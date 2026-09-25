# decision/

Nhận điểm bất thường từ inference/, so với threshold trong config, trả về
1 trong 3 trạng thái: pass | suspect | reject. Log lại mọi quyết định kèm
product_id, mã lô, điểm số — phục vụ truy vết và feedback loop sau này.
