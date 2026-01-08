# WORKFLOW: Medium Scale 2 (80 patients)

## Cấu trúc thư mục
```
rule-based-final/
└── medium scale 2/
    ├── data med 80.py           → Generate data 80 patients
    ├── heuristic_med.py         → Heuristic scheduler
    ├── medium_scale_80p.dat     → Generated data file
    └── medium_scale_result.xlsx → Heuristic output
```

## Bước 1: Generate Data
```bash
cd "rule-based-final/medium scale 2"
python "data med 80.py"
```

**Output:** `medium_scale_80p.dat` (80 patients, 16 surgeons, 5 rooms)

## Bước 2: Chạy Heuristic
```bash
python heuristic_med.py
```

**Output:** `medium_scale_result.xlsx` (~70-80 patients scheduled)

## Bước 3: Chạy GA (cần tạo wrapper script tương tự run_ga_med.py)

**Lưu ý về encoding errors:**
- Script có Vietnamese characters → encoding errors trên Windows console
- Nhưng files vẫn được tạo thành công
- Có thể bỏ qua warnings
