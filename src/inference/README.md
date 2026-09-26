# inference/
Loads the model for a given product_id, runs an image through it, and
returns the anomaly score plus the suspect region (if any). Does NOT decide
pass/fail here — that belongs to decision/.
