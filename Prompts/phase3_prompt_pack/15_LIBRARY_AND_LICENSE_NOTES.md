# Phase 3 Library and License Notes

Verified during prompt-pack creation on 2026-08-21.

## scikit-learn

Role:

- preprocessing;
- train/validation split;
- logistic regression;
- evaluation metrics;
- pipeline/column transformer utilities.

License:

- BSD-style open-source license;
- commercially usable.

Current public documentation observed at pack creation listed scikit-learn 1.9.0 as stable.

Source:
- https://scikit-learn.org/

Do not require exactly 1.9.0 unless the project is actually tested with it. Use a compatible bounded requirement and persist the exact runtime version in model metadata.

## pulearn

Role:

- genuine positive-unlabeled estimators.

Required Phase 3 method:
- `ElkanotoPuClassifier`

Preferred challenger:
- `BaggingPuClassifier`

License:
- BSD 3-Clause.

PyPI release observed at pack creation:
- `pulearn 0.2.0`, released 2026-03-14.

The project documentation also describes Elkan-Noto, Bagging PU, nnPU and PU-oriented diagnostics/model-selection utilities.

Sources:
- https://pypi.org/project/pulearn/
- https://github.com/pulearn/pulearn
- https://pulearn.github.io/pulearn/doc/pulearn/

`pulearn` is marked Beta on PyPI. Treat the exact version as part of the model's reproducibility metadata.

## joblib

Role:

- local serialization of fitted preprocessing + model artifact.

It is already a common dependency in the scikit-learn ecosystem, but Phase 3 should declare/verify it explicitly if imported directly.

## pandas / NumPy

Already present through data-generation requirements.

Phase 3 may use pandas for the **customer-grain** ML frame after SQL has reduced the cohort.

Do not load the entire 570K observation history or 5M prospect universe into pandas merely because pandas is available.

## Open-source-first rule

These libraries are suitable for this POC without introducing a commercial runtime requirement.

If a future commercial ML library is evaluated, keep the algorithm/service interface separable so it can be added as a challenger rather than forcing a rewrite.
