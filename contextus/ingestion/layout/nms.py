class NmsProcessor:
    @staticmethod
    def compute_iou(box_a, box_b) -> float:
        ax0, ay0, ax1, ay1 = box_a
        bx0, by0, bx1, by1 = box_b
        inter_x0 = max(ax0, bx0)
        inter_y0 = max(ay0, by0)
        inter_x1 = min(ax1, bx1)
        inter_y1 = min(ay1, by1)
        if inter_x1 < inter_x0 or inter_y1 < inter_y0:
            return 0.0
        inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
        area_a = (ax1 - ax0) * (ay1 - ay0)
        area_b = (bx1 - bx0) * (by1 - by0)
        return inter_area / (area_a + area_b - inter_area)

    @classmethod
    def deduplicate(cls, detections: list[dict], iou_threshold: float = 0.7) -> list[dict]:
        if not detections:
            return []
        pending = sorted(detections, key=lambda item: item["confidence"], reverse=True)
        kept: list[dict] = []
        while pending:
            best = pending.pop(0)
            kept.append(best)
            pending = [
                item
                for item in pending
                if item["type"] != best["type"]
                or cls.compute_iou(item["bbox"], best["bbox"]) <= iou_threshold
            ]
        return kept
