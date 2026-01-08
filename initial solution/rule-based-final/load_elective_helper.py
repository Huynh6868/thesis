def load_elective_schedule_xlsx(path: str) -> pd.DataFrame:
    """
    Load elective schedule from Excel file and return as DataFrame.
    Used by GA optimizer script.
    
    Expected columns: pid, surgery_type, day, time_hhmm, room, main, assist1, assist2
    """
    import pandas as pd
    df = pd.read_excel(path, sheet_name=0)
    df = df[["pid", "surgery_type", "day", "time_hhmm", "room", "main", "assist1", "assist2"]]
    return df
