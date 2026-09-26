# Safe Retraining Procedure (avoiding a new model that's worse than the old one)

1. A newly trained model is saved to `models/<product_id>/v<n+1>/` — it does
   NOT overwrite `models/<product_id>/v<n>/`, which is the one currently in production.
2. Run `training/evaluate.py` to compare the new model against the old one on
   the latest `confirmed_ng/` + `good/` data.
3. Only switch to the new model when: the escape rate (missed defects) does
   not increase AND the false positive rate does not increase significantly.
4. Update `model.path` in the product's config file to point to the new version.
5. Keep at least the last 2 versions around so you can roll back if a problem
   is found after going to production.

## Data priority when retraining
Data from units returned by customers (real false negatives) is always
prioritized first for the training set, because this is the type of defect
with the most direct business impact — recall the original goal: reducing
defective units that reach the customer.
