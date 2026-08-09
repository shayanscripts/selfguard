"""Upgrade the v3 notebook with leakage-safe text stacking and calibration."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path


def source(value: str) -> list[str]:
    return textwrap.dedent(value).lstrip("\n").splitlines(keepends=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    notebook = json.loads(Path(args.base).read_text(encoding="utf-8"))
    cells = {cell.get("id"): cell for cell in notebook["cells"]}
    cells["install"]["source"] = [
        line.replace("/content/selfguard-v3", "/content/selfguard-v4")
        for line in cells["install"]["source"]
    ]

    cells["intro"]["source"] = source(
        """
        # SELFGuard v4 — leakage-safe text stack development

        V3 improved strict-point SEP recall from 9.5% to 12.25%, but remained
        far below the 50% release gate and its SEP-calibrated prompt threshold
        detected 0/60 attacks on the external deepset test.

        V4 adds a character/word TF-IDF prompt branch trained on SEP train plus
        only the deepset training split. Leakage-safe out-of-fold prompt scores
        are stacked with response and auditable prompt signals. SEP candidate
        and threshold selection remain validation-only at the 1% clean-FPR
        Wilson-upper-bound target. No long response-generation pass is repeated.

        **Development only.** SEP and the deepset test have already been
        inspected. Promotion requires a newly frozen deployment holdout.
        """
    )
    cells["training-heading"]["source"] = source(
        """
        ## Cross-domain text model and leakage-safe stacking

        SEP clean/injected pairs stay together in every out-of-fold split.
        Deepset test rows are excluded from every fit and threshold-selection
        step. Raw text remains in memory and is never exported.
        """
    )
    cells["training"]["source"] = source(
        """
        import time
        from datasets import load_dataset
        from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold, StratifiedKFold
        from sklearn.pipeline import FeatureUnion, Pipeline
        from selfguard import binary_metrics, select_threshold_at_fpr

        DEEPSET_DATASET = 'deepset/prompt-injections'
        DEEPSET_REVISION = '4f61ecb038e9c3fb77e21034b22511b523772cdd'
        external_dataset = load_dataset(DEEPSET_DATASET, revision=DEEPSET_REVISION)
        external_train = external_dataset['train'].to_pandas()[['text', 'label']].copy()
        external_test = external_dataset['test'].to_pandas()[['text', 'label']].copy()
        normalize = lambda value: ' '.join(str(value).casefold().split())
        train_hashes = {hashlib.sha256(normalize(text).encode()).hexdigest() for text in external_train.text}
        test_hashes = {hashlib.sha256(normalize(text).encode()).hexdigest() for text in external_test.text}
        assert not train_hashes & test_hashes, 'Exact deepset train/test text overlap'

        train = frame[frame.split == 'train'].copy()
        validation = frame[frame.split == 'validation'].copy()
        test = frame[frame.split == 'test'].copy()
        train_text = np.asarray([prompt_texts[index] for index in train.index], dtype=object)
        validation_text = np.asarray([prompt_texts[index] for index in validation.index], dtype=object)
        test_text = np.asarray([prompt_texts[index] for index in test.index], dtype=object)
        sep_hashes = {
            hashlib.sha256(normalize(text).encode()).hexdigest()
            for text in np.concatenate([train_text, validation_text, test_text])
        }
        assert not sep_hashes & (train_hashes | test_hashes), 'Exact SEP/deepset text overlap'

        def new_text_model():
            features = FeatureUnion([
                ('char', TfidfVectorizer(
                    analyzer='char_wb', ngram_range=(3, 5), min_df=2,
                    max_features=75000, sublinear_tf=True, strip_accents='unicode',
                )),
                ('word', TfidfVectorizer(
                    analyzer='word', ngram_range=(1, 2), min_df=2,
                    max_features=30000, sublinear_tf=True, strip_accents='unicode',
                )),
            ])
            classifier = LogisticRegression(
                C=2.0, class_weight='balanced', solver='liblinear',
                max_iter=1000, random_state=SEED,
            )
            return Pipeline([('features', features), ('classifier', classifier)])

        fit_started = time.perf_counter()
        external_text = external_train.text.astype(str).to_numpy()
        external_label = external_train.label.astype(int).to_numpy()

        # OOF scores prevent the stacker from learning from in-sample text scores.
        sep_oof_score = np.zeros(len(train), dtype=float)
        group_folds = GroupKFold(n_splits=5)
        for fold, (fit_index, score_index) in enumerate(
            group_folds.split(train_text, train.label.to_numpy(), train.pair_id.to_numpy())
        ):
            fold_model = new_text_model()
            fold_model.fit(
                np.concatenate([train_text[fit_index], external_text]),
                np.concatenate([train.label.to_numpy()[fit_index], external_label]),
            )
            sep_oof_score[score_index] = fold_model.predict_proba(train_text[score_index])[:, 1]

        # OOF deepset-train scores support domain-specific development calibration.
        external_oof_score = np.zeros(len(external_train), dtype=float)
        external_folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
        for fit_index, score_index in external_folds.split(external_text, external_label):
            fold_model = new_text_model()
            fold_model.fit(
                np.concatenate([train_text, external_text[fit_index]]),
                np.concatenate([train.label.to_numpy(), external_label[fit_index]]),
            )
            external_oof_score[score_index] = fold_model.predict_proba(external_text[score_index])[:, 1]

        text_model = new_text_model()
        text_model.fit(
            np.concatenate([train_text, external_text]),
            np.concatenate([train.label.to_numpy(), external_label]),
        )
        train['prompt_text_score'] = sep_oof_score
        validation['prompt_text_score'] = text_model.predict_proba(validation_text)[:, 1]
        test['prompt_text_score'] = text_model.predict_proba(test_text)[:, 1]
        frame.loc[train.index, 'prompt_text_score'] = train.prompt_text_score
        frame.loc[validation.index, 'prompt_text_score'] = validation.prompt_text_score
        frame.loc[test.index, 'prompt_text_score'] = test.prompt_text_score

        def rf(seed=SEED):
            return RandomForestClassifier(
                n_estimators=600, max_depth=9, min_samples_leaf=2,
                class_weight='balanced_subsample', max_features=None,
                random_state=seed, n_jobs=-1,
            )

        response_model = rf(SEED)
        response_model.fit(train[response_features], train.label)
        prompt_numeric_model = ExtraTreesClassifier(
            n_estimators=700, max_depth=12, min_samples_leaf=2,
            class_weight='balanced', max_features=None,
            random_state=SEED + 1, n_jobs=-1,
        )
        prompt_numeric_model.fit(train[prompt_features], train.label)

        stacked_features = response_features + prompt_features + ['prompt_text_score']
        provisional = ExtraTreesClassifier(
            n_estimators=400, max_depth=10, min_samples_leaf=3,
            class_weight='balanced', max_features=None,
            random_state=SEED + 2, n_jobs=-1,
        )
        provisional.fit(train[stacked_features], train.label)
        provisional_score = provisional.predict_proba(train[stacked_features])[:, 1]
        clean_mask = train.label.to_numpy() == 0
        hard_cutoff = float(np.quantile(provisional_score[clean_mask], 0.85))
        hard_negative = clean_mask & (provisional_score >= hard_cutoff)
        sample_weight = np.ones(len(train), dtype=float)
        sample_weight[hard_negative] = 10.0

        stacked_model = ExtraTreesClassifier(
            n_estimators=1000, max_depth=14, min_samples_leaf=3,
            class_weight='balanced', max_features=None,
            random_state=SEED + 3, n_jobs=-1,
        )
        stacked_model.fit(
            train[stacked_features], train.label, sample_weight=sample_weight
        )
        training_seconds = time.perf_counter() - fit_started
        print('SEP OOF folds: 5; deepset OOF folds: 5')
        print('Mined hard negatives:', int(hard_negative.sum()), '/', int(clean_mask.sum()))
        print('Training seconds:', round(training_seconds, 2))
        """
    )
    cells["selection"]["source"] = source(
        """
        candidate_models = {
            'response_rf': (response_model, response_features),
            'prompt_numeric_et': (prompt_numeric_model, prompt_features),
            'stacked_text_hnm_et': (stacked_model, stacked_features),
        }
        validation_scores = {
            name: model.predict_proba(validation[features])[:, 1]
            for name, (model, features) in candidate_models.items()
        }
        validation_scores['prompt_tfidf_lr'] = validation.prompt_text_score.to_numpy()

        candidate_rows = []
        selections = {}
        for name, score in validation_scores.items():
            selection = select_threshold_at_fpr(
                validation.label, score, TARGET_CLEAN_FPR,
                confidence=0.95, fpr_constraint='upper',
            )
            selections[name] = selection
            candidate_rows.append({
                'candidate': name,
                'threshold': selection.threshold,
                'validation_recall': selection.validation.recall.value,
                'validation_f1': selection.validation.f1,
                'validation_fpr': selection.validation.clean_fpr.value,
                'validation_fpr_high': selection.validation.clean_fpr.high,
                'validation_roc_auc': selection.validation.roc_auc,
                'validation_average_precision': selection.validation.average_precision,
            })
        candidate_table = pd.DataFrame(candidate_rows)
        winner_name = max(
            candidate_rows,
            key=lambda row: (
                row['validation_recall'], row['validation_f1'],
                row['validation_average_precision'], row['candidate'],
            ),
        )['candidate']
        winner_selection = selections[winner_name]

        def candidate_score(name, subset):
            if name == 'prompt_tfidf_lr':
                return subset.prompt_text_score.to_numpy()
            model, features = candidate_models[name]
            return model.predict_proba(subset[features])[:, 1]

        test_score = candidate_score(winner_name, test)
        descriptive_test = binary_metrics(
            test.label, test_score, winner_selection.threshold,
            deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
        )
        score_frame = frame[['pair_id', 'split', 'label', 'attack_effective']].copy()
        for name in validation_scores:
            score_frame[name + '_score'] = np.nan
            for split_name, subset in (('train', train), ('validation', validation), ('test', test)):
                score_frame.loc[subset.index, name + '_score'] = candidate_score(name, subset)
        assert np.isfinite(score_frame.filter(like='_score').to_numpy()).all()
        display(candidate_table.sort_values(['validation_recall', 'validation_f1'], ascending=False))
        print('Validation-selected winner:', winner_name)
        print(json.dumps({
            'status': 'descriptive_already_inspected_sep_test',
            'candidate': winner_name,
            'threshold': winner_selection.threshold,
            'test': descriptive_test.__dict__,
        }, default=lambda item: item.__dict__, indent=2, allow_nan=False))
        """
    )
    cells["external-heading"]["source"] = source(
        """
        ## Domain-calibrated external development diagnostic

        The text model never fits the deepset test. Its external operating point
        is selected from out-of-fold deepset-training predictions. This test has
        already been inspected in v3, so the result remains development-only.
        """
    )
    cells["external"]["source"] = source(
        """
        def best_f1_selection(labels, scores):
            best = None
            for threshold in np.unique(np.asarray(scores, dtype=float)):
                metrics = binary_metrics(
                    labels, scores, float(threshold),
                    deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
                )
                candidate = (metrics.f1, metrics.recall.value, float(threshold), metrics)
                if best is None or candidate[:3] > best[:3]:
                    best = candidate
            return best[2], best[3]

        external_threshold, external_oof_metrics = best_f1_selection(
            external_label, external_oof_score
        )
        external_test_score = text_model.predict_proba(
            external_test.text.astype(str).to_numpy()
        )[:, 1]
        external_metrics_domain = binary_metrics(
            external_test.label, external_test_score, external_threshold,
            deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
        )
        sep_prompt_threshold = selections['prompt_tfidf_lr'].threshold
        external_metrics_sep_threshold = binary_metrics(
            external_test.label, external_test_score, sep_prompt_threshold,
            deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
        )
        external_digest = hashlib.sha256(
            '\\n'.join(
                json.dumps({'text': row.text, 'label': int(row.label)}, sort_keys=True)
                for row in external_test.itertuples(index=False)
            ).encode('utf-8')
        ).hexdigest()

        def json_safe(value):
            if hasattr(value, '__dict__'):
                return json_safe(value.__dict__)
            if isinstance(value, dict):
                return {str(key): json_safe(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [json_safe(item) for item in value]
            if isinstance(value, np.generic):
                return json_safe(value.item())
            if isinstance(value, float) and not math.isfinite(value):
                return None
            return value

        print(json.dumps(json_safe({
            'dataset': DEEPSET_DATASET,
            'revision': DEEPSET_REVISION,
            'test_rows': len(external_test),
            'canonical_test_rows_sha256': external_digest,
            'domain_threshold_selected_on': 'deepset train OOF predictions',
            'domain_oof_metrics': external_oof_metrics,
            'test_at_domain_threshold': external_metrics_domain,
            'test_at_sep_strict_threshold': external_metrics_sep_threshold,
        }), indent=2, allow_nan=False))
        """
    )
    cells["custom-heading"]["source"] = source(
        """
        ## Optional sealed deployment calibration and test

        Provide JSON Lines with `text`, `label`, `group_id`, `stratum`,
        `is_hard_negative`, and `split` (`calibration` or `test`). Source groups
        must not cross the two splits. The threshold is selected on calibration
        and applied once to test.
        """
    )
    cells["custom"]["source"] = source(
        """
        EXTERNAL_JSONL = None  # Example: '/content/deployment_holdout.jsonl'
        deployment_holdout_metrics = None
        deployment_selection = None
        if EXTERNAL_JSONL:
            holdout = pd.read_json(EXTERNAL_JSONL, lines=True)
            required = {'text', 'label', 'group_id', 'stratum', 'is_hard_negative', 'split'}
            assert required.issubset(holdout.columns), required - set(holdout.columns)
            assert set(holdout.split) == {'calibration', 'test'}
            assert holdout.group_id.astype(str).str.len().gt(0).all()
            assert set(holdout.label.unique()).issubset({0, 1})
            assert not ((holdout.is_hard_negative) & (holdout.label != 0)).any()
            calibration_groups = set(holdout.loc[holdout.split == 'calibration', 'group_id'])
            test_groups = set(holdout.loc[holdout.split == 'test', 'group_id'])
            assert not calibration_groups & test_groups, 'group_id crosses calibration/test'
            calibration = holdout[holdout.split == 'calibration'].copy()
            holdout_test = holdout[holdout.split == 'test'].copy()
            calibration_score = text_model.predict_proba(calibration.text.astype(str))[:, 1]
            holdout_test_score = text_model.predict_proba(holdout_test.text.astype(str))[:, 1]
            deployment_selection = select_threshold_at_fpr(
                calibration.label, calibration_score, TARGET_CLEAN_FPR,
                confidence=0.95, fpr_constraint='upper',
            )
            deployment_holdout_metrics = binary_metrics(
                holdout_test.label, holdout_test_score, deployment_selection.threshold,
                deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
            )
            print(json.dumps(json_safe({
                'selection': deployment_selection,
                'test': deployment_holdout_metrics,
            }), indent=2, allow_nan=False))
        else:
            print('No sealed deployment calibration/test supplied; promotion remains blocked.')
        """
    )
    cells["export"]["source"] = source(
        """
        import importlib.metadata, joblib, platform

        OUTPUT_DIR = ROOT / 'output-v4'
        OUTPUT_DIR.mkdir(exist_ok=True)
        artifact_path = OUTPUT_DIR / 'selfguard_v4_development_model.joblib'
        metrics_path = OUTPUT_DIR / 'selfguard_v4_development_metrics.json'
        scores_path = OUTPUT_DIR / 'selfguard_v4_candidate_scores.csv'
        hash_path = OUTPUT_DIR / 'selfguard_v4_sha256.json'
        zip_path = pathlib.Path('/content/selfguard_v4_development_analytics.zip')

        score_frame.to_csv(scores_path, index=False)
        joblib.dump({
            'status': 'development_not_promotion_eligible',
            'winner_name': winner_name,
            'winner_threshold': winner_selection.threshold,
            'candidate_models': candidate_models,
            'text_model': text_model,
            'features': {
                'response': response_features,
                'prompt_numeric': prompt_features,
                'stacked': stacked_features,
            },
            'external_domain_threshold': external_threshold,
            'system_prompt': SYSTEM_PROMPT,
            'sep_dataset_sha256': SEP_SHA256,
            'sep_dataset_commit': SEP_COMMIT,
            'deepset_revision': DEEPSET_REVISION,
            'seed': SEED,
        }, artifact_path, compress=3)
        payload = {
            'schema_version': 4,
            'status': 'development_not_promotion_eligible',
            'reason': 'SEP and deepset tests previously inspected; no sealed deployment holdout',
            'target_clean_fpr': TARGET_CLEAN_FPR,
            'candidate_table': candidate_table.to_dict(orient='records'),
            'winner': winner_name,
            'winner_threshold': winner_selection.threshold,
            'descriptive_sep_test': descriptive_test,
            'external_deepset': {
                'dataset': DEEPSET_DATASET,
                'revision': DEEPSET_REVISION,
                'test_rows': len(external_test),
                'canonical_test_rows_sha256': external_digest,
                'domain_threshold': external_threshold,
                'domain_oof_metrics': external_oof_metrics,
                'test_at_domain_threshold': external_metrics_domain,
                'test_at_sep_strict_threshold': external_metrics_sep_threshold,
            },
            'deployment_holdout': deployment_holdout_metrics,
            'training_seconds': training_seconds,
            'hard_negative_count': int(hard_negative.sum()),
            'stacked_feature_importance': dict(zip(
                stacked_features, stacked_model.feature_importances_.tolist()
            )),
            'environment': {
                'python': platform.python_version(),
                'scikit_learn': importlib.metadata.version('scikit-learn'),
                'sentence_transformers': importlib.metadata.version('sentence-transformers'),
                'datasets': importlib.metadata.version('datasets'),
                'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            },
        }
        metrics_path.write_text(
            json.dumps(json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + '\\n',
            encoding='utf-8',
        )
        exports = [artifact_path, metrics_path, scores_path]
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in exports}
        hash_path.write_text(
            json.dumps({'schema_version': 4, 'algorithm': 'sha256', 'sha256': hashes}, indent=2) + '\\n',
            encoding='utf-8',
        )
        exports.append(hash_path)
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in exports:
                archive.write(path, arcname=path.name)
        print('Development archive:', zip_path)
        print('Production promotion eligible: False')
        """
    )

    notebook["metadata"]["colab"]["name"] = Path(args.output).name
    Path(args.output).write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
