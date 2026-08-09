"""Build the v5 ensemble and plug-in artifact notebook from the v4 notebook."""

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
        line.replace("/content/selfguard-v4", "/content/selfguard-v5").replace(
            '"joblib>=1.3,<2"', '"joblib>=1.3,<2" "skops>=0.10,<1"'
        )
        for line in cells["install"]["source"]
    ]
    cells["intro"]["source"] = source(
        """
        # SELFGuard v5 — ensemble plug-in candidate

        V4 reached descriptive F1 0.7958 and recall 66.25%, but one clean false
        positive made the final FPR confidence bound exceed 1%. V5 fixes the
        tied-quantile hard-negative bug, adds four diverse prompt classifiers,
        and evaluates prompt-only soft voting plus prompt/response stackers.

        The plug-in candidate is exported using hash-verified `skops` rather
        than executable pickle/joblib. It can wrap any Python LLM callable
        before the model request is made.

        **Development only:** SEP and deepset test results are already exposed.
        F1 0.86–0.88 is a development target, not a guaranteed result or a
        substitute for tool authorization and sandboxing.
        """
    )
    cells["training-heading"]["source"] = source(
        """
        ## Diverse text ensemble with exact hard-negative mining

        Each base text learner receives group-safe out-of-fold SEP scores.
        Exact stable top-k selection guarantees that precisely 15% of clean
        training rows receive the hard-negative weight, even when scores tie.
        """
    )
    cells["training"]["source"] = source(
        """
        import time
        from datasets import load_dataset
        from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, VotingClassifier
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold, StratifiedKFold
        from sklearn.naive_bayes import ComplementNB
        from sklearn.pipeline import FeatureUnion, Pipeline
        from sklearn.preprocessing import StandardScaler
        from selfguard import binary_metrics, select_threshold_at_fpr

        DEEPSET_DATASET = 'deepset/prompt-injections'
        DEEPSET_REVISION = '4f61ecb038e9c3fb77e21034b22511b523772cdd'
        external_dataset = load_dataset(DEEPSET_DATASET, revision=DEEPSET_REVISION)
        external_train = external_dataset['train'].to_pandas()[['text', 'label']].copy()
        external_test = external_dataset['test'].to_pandas()[['text', 'label']].copy()
        normalize = lambda value: ' '.join(str(value).casefold().split())
        external_train_hashes = {
            hashlib.sha256(normalize(text).encode()).hexdigest() for text in external_train.text
        }
        external_test_hashes = {
            hashlib.sha256(normalize(text).encode()).hexdigest() for text in external_test.text
        }
        assert not external_train_hashes & external_test_hashes

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
        assert not sep_hashes & (external_train_hashes | external_test_hashes)
        external_text = external_train.text.astype(str).to_numpy()
        external_label = external_train.label.astype(int).to_numpy()

        def charword_lr():
            return Pipeline([
                ('features', FeatureUnion([
                    ('char', TfidfVectorizer(
                        analyzer='char_wb', ngram_range=(3, 5), min_df=2,
                        max_features=80000, sublinear_tf=True, strip_accents='unicode',
                    )),
                    ('word', TfidfVectorizer(
                        analyzer='word', ngram_range=(1, 2), min_df=2,
                        max_features=35000, sublinear_tf=True, strip_accents='unicode',
                    )),
                ])),
                ('classifier', LogisticRegression(
                    C=2.0, class_weight='balanced', solver='liblinear',
                    max_iter=1200, random_state=SEED,
                )),
            ])

        def char_lr():
            return Pipeline([
                ('features', TfidfVectorizer(
                    analyzer='char_wb', ngram_range=(2, 6), min_df=2,
                    max_features=120000, sublinear_tf=True, strip_accents='unicode',
                )),
                ('classifier', LogisticRegression(
                    C=1.0, class_weight='balanced', solver='liblinear',
                    max_iter=1200, random_state=SEED + 1,
                )),
            ])

        def word_lr():
            return Pipeline([
                ('features', TfidfVectorizer(
                    analyzer='word', ngram_range=(1, 3), min_df=2,
                    max_features=70000, sublinear_tf=True, strip_accents='unicode',
                )),
                ('classifier', LogisticRegression(
                    C=1.5, class_weight='balanced', solver='liblinear',
                    max_iter=1200, random_state=SEED + 2,
                )),
            ])

        def charword_nb():
            return Pipeline([
                ('features', FeatureUnion([
                    ('char', TfidfVectorizer(
                        analyzer='char_wb', ngram_range=(3, 5), min_df=2,
                        max_features=80000, sublinear_tf=True, strip_accents='unicode',
                    )),
                    ('word', TfidfVectorizer(
                        analyzer='word', ngram_range=(1, 2), min_df=2,
                        max_features=35000, sublinear_tf=True, strip_accents='unicode',
                    )),
                ])),
                ('classifier', ComplementNB(alpha=0.35)),
            ])

        text_factories = {
            'prompt_charword_lr': charword_lr,
            'prompt_char_lr': char_lr,
            'prompt_word_lr': word_lr,
            'prompt_charword_nb': charword_nb,
        }
        fit_started = time.perf_counter()
        train_labels = train.label.to_numpy()
        sep_oof = {name: np.zeros(len(train)) for name in text_factories}
        for fit_index, score_index in GroupKFold(n_splits=5).split(
            train_text, train_labels, train.pair_id.to_numpy()
        ):
            for name, factory in text_factories.items():
                model = factory()
                model.fit(
                    np.concatenate([train_text[fit_index], external_text]),
                    np.concatenate([train_labels[fit_index], external_label]),
                )
                sep_oof[name][score_index] = model.predict_proba(train_text[score_index])[:, 1]

        external_oof = {name: np.zeros(len(external_train)) for name in text_factories}
        for fit_index, score_index in StratifiedKFold(
            n_splits=5, shuffle=True, random_state=SEED
        ).split(external_text, external_label):
            for name, factory in text_factories.items():
                model = factory()
                model.fit(
                    np.concatenate([train_text, external_text[fit_index]]),
                    np.concatenate([train_labels, external_label[fit_index]]),
                )
                external_oof[name][score_index] = model.predict_proba(
                    external_text[score_index]
                )[:, 1]

        fit_text = np.concatenate([train_text, external_text])
        fit_label = np.concatenate([train_labels, external_label])
        text_models = {}
        for name, factory in text_factories.items():
            text_models[name] = factory().fit(fit_text, fit_label)
            train[name + '_score'] = sep_oof[name]
            validation[name + '_score'] = text_models[name].predict_proba(validation_text)[:, 1]
            test[name + '_score'] = text_models[name].predict_proba(test_text)[:, 1]

        vote_estimators = [(name, factory()) for name, factory in text_factories.items()]
        prompt_voting_model = VotingClassifier(estimators=vote_estimators, voting='soft')
        prompt_voting_model.fit(fit_text, fit_label)
        train['prompt_soft_vote_score'] = np.mean(
            np.column_stack([sep_oof[name] for name in text_factories]), axis=1
        )
        validation['prompt_soft_vote_score'] = prompt_voting_model.predict_proba(validation_text)[:, 1]
        test['prompt_soft_vote_score'] = prompt_voting_model.predict_proba(test_text)[:, 1]
        direct_vote = np.mean(np.column_stack([
            validation[name + '_score'].to_numpy() for name in text_factories
        ]), axis=1)
        assert np.allclose(direct_vote, validation.prompt_soft_vote_score, atol=1e-10)

        response_model = RandomForestClassifier(
            n_estimators=700, max_depth=9, min_samples_leaf=2,
            class_weight='balanced_subsample', max_features=None,
            random_state=SEED, n_jobs=-1,
        ).fit(train[response_features], train.label)

        text_score_features = [name + '_score' for name in text_factories] + [
            'prompt_soft_vote_score'
        ]
        stacked_features = response_features + prompt_features + text_score_features
        provisional = ExtraTreesClassifier(
            n_estimators=400, max_depth=10, min_samples_leaf=3,
            class_weight='balanced', max_features=None,
            random_state=SEED + 10, n_jobs=-1,
        ).fit(train[stacked_features], train.label)
        provisional_score = provisional.predict_proba(train[stacked_features])[:, 1]
        clean_indices = np.flatnonzero(train.label.to_numpy() == 0)
        hard_count = int(math.ceil(0.15 * len(clean_indices)))
        ranked_clean = clean_indices[
            np.argsort(provisional_score[clean_indices], kind='mergesort')
        ]
        hard_indices = ranked_clean[-hard_count:]
        hard_negative = np.zeros(len(train), dtype=bool)
        hard_negative[hard_indices] = True
        assert int(hard_negative.sum()) == hard_count == 150
        sample_weight = np.ones(len(train), dtype=float)
        sample_weight[hard_negative] = 10.0

        stacked_model = ExtraTreesClassifier(
            n_estimators=1200, max_depth=15, min_samples_leaf=3,
            class_weight='balanced', max_features=None,
            random_state=SEED + 11, n_jobs=-1,
        ).fit(train[stacked_features], train.label, sample_weight=sample_weight)
        meta_model = Pipeline([
            ('scale', StandardScaler()),
            ('classifier', LogisticRegression(
                C=0.75, class_weight='balanced', solver='liblinear',
                max_iter=1000, random_state=SEED + 12,
            )),
        ]).fit(train[stacked_features], train.label)
        training_seconds = time.perf_counter() - fit_started
        print('Exact hard negatives:', int(hard_negative.sum()))
        print('Training seconds:', round(training_seconds, 2))
        """
    )
    cells["selection"]["source"] = source(
        """
        candidate_scores = {
            'response_rf': response_model.predict_proba(validation[response_features])[:, 1],
            'stacked_exact_hnm_et': stacked_model.predict_proba(validation[stacked_features])[:, 1],
            'stacked_meta_lr': meta_model.predict_proba(validation[stacked_features])[:, 1],
            'prompt_soft_vote': validation.prompt_soft_vote_score.to_numpy(),
        }
        for name in text_factories:
            candidate_scores[name] = validation[name + '_score'].to_numpy()

        candidate_rows, selections = [], {}
        for name, score in candidate_scores.items():
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
        winner_name = max(candidate_rows, key=lambda row: (
            row['validation_recall'], row['validation_f1'],
            row['validation_average_precision'], row['candidate'],
        ))['candidate']
        prompt_names = list(text_factories) + ['prompt_soft_vote']
        plugin_name = max(
            (row for row in candidate_rows if row['candidate'] in prompt_names),
            key=lambda row: (
                row['validation_recall'], row['validation_f1'],
                row['validation_average_precision'], row['candidate'],
            ),
        )['candidate']
        winner_selection = selections[winner_name]
        plugin_selection = selections[plugin_name]
        plugin_model = (
            prompt_voting_model if plugin_name == 'prompt_soft_vote'
            else text_models[plugin_name]
        )

        def score_candidate(name, subset):
            if name == 'response_rf':
                return response_model.predict_proba(subset[response_features])[:, 1]
            if name == 'stacked_exact_hnm_et':
                return stacked_model.predict_proba(subset[stacked_features])[:, 1]
            if name == 'stacked_meta_lr':
                return meta_model.predict_proba(subset[stacked_features])[:, 1]
            if name == 'prompt_soft_vote':
                return subset.prompt_soft_vote_score.to_numpy()
            return subset[name + '_score'].to_numpy()

        test_score = score_candidate(winner_name, test)
        descriptive_test = binary_metrics(
            test.label, test_score, winner_selection.threshold,
            deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
        )
        plugin_test = binary_metrics(
            test.label, score_candidate(plugin_name, test), plugin_selection.threshold,
            deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
        )
        score_frame = frame[['pair_id', 'split', 'label', 'attack_effective']].copy()
        for name in candidate_scores:
            score_frame[name + '_score'] = np.nan
            for subset in (train, validation, test):
                score_frame.loc[subset.index, name + '_score'] = score_candidate(name, subset)
        assert np.isfinite(score_frame.filter(like='_score').to_numpy()).all()
        display(candidate_table.sort_values(['validation_recall', 'validation_f1'], ascending=False))
        print('Overall winner:', winner_name)
        print('Plug-in prompt-only winner:', plugin_name)
        print(json.dumps({
            'status': 'descriptive_already_inspected_sep_test',
            'overall_test': descriptive_test,
            'plugin_test': plugin_test,
        }, default=lambda item: item.__dict__, indent=2, allow_nan=False))
        """
    )
    cells["external-heading"]["source"] = source(
        """
        ## External-domain calibration for the prompt plug-in candidate

        The deepset test is excluded from all fitting and calibration. Because
        it was already inspected in v3/v4, it remains development evidence.
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

        if plugin_name == 'prompt_soft_vote':
            plugin_external_oof = np.mean(np.column_stack([
                external_oof[name] for name in text_factories
            ]), axis=1)
        else:
            plugin_external_oof = external_oof[plugin_name]
        external_threshold, external_oof_metrics = best_f1_selection(
            external_label, plugin_external_oof
        )
        external_test_score = plugin_model.predict_proba(
            external_test.text.astype(str).to_numpy()
        )[:, 1]
        external_metrics_domain = binary_metrics(
            external_test.label, external_test_score, external_threshold,
            deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
        )
        external_metrics_sep_threshold = binary_metrics(
            external_test.label, external_test_score, plugin_selection.threshold,
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
            'plugin_candidate': plugin_name,
            'domain_threshold': external_threshold,
            'domain_oof_metrics': external_oof_metrics,
            'test_at_domain_threshold': external_metrics_domain,
            'test_at_sep_strict_threshold': external_metrics_sep_threshold,
        }), indent=2, allow_nan=False))
        """
    )
    cells["custom"]["source"] = source(
        """
        EXTERNAL_JSONL = None  # calibration/test JSONL described above
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
            calibration = holdout[holdout.split == 'calibration'].copy()
            holdout_test = holdout[holdout.split == 'test'].copy()
            assert not set(calibration.group_id) & set(holdout_test.group_id)
            calibration_score = plugin_model.predict_proba(calibration.text.astype(str))[:, 1]
            holdout_test_score = plugin_model.predict_proba(holdout_test.text.astype(str))[:, 1]
            deployment_selection = select_threshold_at_fpr(
                calibration.label, calibration_score, TARGET_CLEAN_FPR,
                confidence=0.95, fpr_constraint='upper',
            )
            deployment_holdout_metrics = binary_metrics(
                holdout_test.label, holdout_test_score, deployment_selection.threshold,
                deployment_attack_prevalence=DEPLOYMENT_ATTACK_PREVALENCE,
            )
            print(json.dumps(json_safe({
                'selection': deployment_selection, 'test': deployment_holdout_metrics,
            }), indent=2, allow_nan=False))
        else:
            print('No sealed deployment calibration/test supplied; promotion remains blocked.')
        """
    )
    cells["export"]["source"] = source(
        """
        import importlib.metadata, io, joblib, platform, skops.io as skops_io

        OUTPUT_DIR = ROOT / 'output-v5'
        OUTPUT_DIR.mkdir(exist_ok=True)
        metrics_path = OUTPUT_DIR / 'selfguard_v5_development_metrics.json'
        scores_path = OUTPUT_DIR / 'selfguard_v5_candidate_scores.csv'
        model_path = OUTPUT_DIR / 'model.skops'
        bundle_metadata_path = OUTPUT_DIR / 'metadata.json'
        bundle_hash_path = OUTPUT_DIR / 'sha256.json'
        plugin_bundle_path = OUTPUT_DIR / 'selfguard_prompt_plugin_candidate.sgplugin'
        analytics_hash_path = OUTPUT_DIR / 'selfguard_v5_sha256.json'
        zip_path = pathlib.Path('/content/selfguard_v5_development_analytics.zip')

        score_frame.to_csv(scores_path, index=False)
        skops_io.dump(plugin_model, model_path)
        trusted_types = sorted(skops_io.get_untrusted_types(file=model_path))
        assert all(item.startswith(('sklearn.', 'numpy.', 'scipy.')) for item in trusted_types)
        plugin_metadata = {
            'schema_version': 1,
            'status': 'development_not_promotion_eligible',
            'model_name': plugin_name,
            'positive_class_index': 1,
            'block_threshold': plugin_selection.threshold,
            'review_threshold': min(plugin_selection.threshold, external_threshold),
            'trusted_types': trusted_types,
            'training_sources': {
                'sep_commit': SEP_COMMIT,
                'sep_sha256': SEP_SHA256,
                'deepset_revision': DEEPSET_REVISION,
            },
        }
        bundle_metadata_path.write_text(
            json.dumps(plugin_metadata, indent=2, sort_keys=True) + '\\n', encoding='utf-8'
        )
        bundle_hashes = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (model_path, bundle_metadata_path)
        }
        bundle_hash_path.write_text(
            json.dumps({'algorithm': 'sha256', 'sha256': bundle_hashes}, indent=2) + '\\n',
            encoding='utf-8',
        )
        with zipfile.ZipFile(plugin_bundle_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in (model_path, bundle_metadata_path, bundle_hash_path):
                archive.write(path, arcname=path.name)

        payload = {
            'schema_version': 5,
            'status': 'development_not_promotion_eligible',
            'target_f1': [0.86, 0.88],
            'target_clean_fpr': TARGET_CLEAN_FPR,
            'candidate_table': candidate_table.to_dict(orient='records'),
            'winner': winner_name,
            'plugin_candidate': plugin_name,
            'plugin_threshold': plugin_selection.threshold,
            'descriptive_sep_test': descriptive_test,
            'plugin_descriptive_sep_test': plugin_test,
            'external_deepset': {
                'revision': DEEPSET_REVISION,
                'canonical_test_rows_sha256': external_digest,
                'domain_threshold': external_threshold,
                'domain_oof_metrics': external_oof_metrics,
                'test_at_domain_threshold': external_metrics_domain,
                'test_at_sep_strict_threshold': external_metrics_sep_threshold,
            },
            'deployment_holdout': deployment_holdout_metrics,
            'training_seconds': training_seconds,
            'hard_negative_count': int(hard_negative.sum()),
            'plugin_bundle_sha256': hashlib.sha256(plugin_bundle_path.read_bytes()).hexdigest(),
            'environment': {
                'python': platform.python_version(),
                'scikit_learn': importlib.metadata.version('scikit-learn'),
                'skops': importlib.metadata.version('skops'),
                'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            },
        }
        metrics_path.write_text(
            json.dumps(json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + '\\n',
            encoding='utf-8',
        )
        exports = [plugin_bundle_path, metrics_path, scores_path]
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in exports}
        analytics_hash_path.write_text(
            json.dumps({'schema_version': 5, 'algorithm': 'sha256', 'sha256': hashes}, indent=2) + '\\n',
            encoding='utf-8',
        )
        exports.append(analytics_hash_path)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in exports:
                archive.write(path, arcname=path.name)
        print('Analytics:', zip_path)
        print('Plug-in bundle member:', plugin_bundle_path.name)
        print('Production promotion eligible: False')
        """
    )
    notebook["metadata"]["colab"]["name"] = Path(args.output).name
    Path(args.output).write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
