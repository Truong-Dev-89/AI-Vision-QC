# decision/
Takes the anomaly score from inference/, compares it against the config's
threshold, and returns one of: pass | suspect | reject. Every decision is
logged with the product_id, serial number, and score — needed for
traceability and the feedback loop later.
