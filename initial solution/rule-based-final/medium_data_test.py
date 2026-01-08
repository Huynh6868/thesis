import random

# ==========================================
# CẤU HÌNH MEDIUM SCALE
# ==========================================
NUM_PATIENTS = 50
NUM_SURGEONS = 12
NUM_DAYS = 5
NUM_ROOMS = 3
DAY_MINUTES = 480 

# Tham số thời gian (Type 1..10)
DURATIONS = [60, 65, 30, 30, 90, 100, 160, 90, 65, 30]
PREP_TIMES = [10, 10, 10, 10, 10, 15, 15, 15, 15, 15]
REST_TIMES = [15, 15, 15, 15, 15, 30, 30, 20, 20, 10]

def generate_medium_dat(filename="medium_scale_50p.dat"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write("/*********************************************\n")
        f.write(f" * MEDIUM SCALE DATASET (For Heuristic/GA Test)\n")
        f.write(f" * Patients: {NUM_PATIENTS}, Surgeons: {NUM_SURGEONS}, Rooms: {NUM_ROOMS}\n")
        f.write(f" *********************************************/\n\n")

        # 1. SETS
        f.write(f"P = {{ {', '.join(str(i) for i in range(1, NUM_PATIENTS + 1))} }};\n")
        f.write(f"S = {{ {', '.join(str(i) for i in range(1, NUM_SURGEONS + 1))} }};\n")
        f.write(f"D = {{ {', '.join(str(i) for i in range(1, NUM_DAYS + 1))} }};\n")
        f.write(f"K = {{ {', '.join(str(i) for i in range(1, NUM_ROOMS + 1))} }};\n\n")
        
        f.write("SurgeryTypes = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};\n")
        
        # 2. PARAMETERS
        wh_str = ", ".join([str(DAY_MINUTES)] * NUM_DAYS)
        f.write(f"wh = [{wh_str}];\n\n")

        f.write(f"DurationByType = [{', '.join(map(str, DURATIONS))}];\n")
        f.write(f"PrepType = [{', '.join(map(str, PREP_TIMES))}];\n")
        f.write(f"RestingTimeByType = [{', '.join(map(str, REST_TIMES))}];\n\n")

        # 3. PATIENT TYPES (Random nhưng có trọng số để giống thực tế)
        # Các ca ngắn (Type 3,4,10) nhiều hơn ca đại phẫu (Type 7)
        types = []
        for _ in range(NUM_PATIENTS):
            t = random.choices(range(1, 11), weights=[10, 10, 15, 15, 10, 8, 5, 8, 10, 15])[0]
            types.append(t)
        
        f.write("PatientType = [\n")
        # Format đẹp: 10 số 1 dòng
        for i in range(0, NUM_PATIENTS, 10):
            chunk = types[i:i+10]
            f.write("  " + ", ".join(map(str, chunk)) + ("," if i+10 < NUM_PATIENTS else "") + "\n")
        f.write("];\n\n")

        # 4. AVAILABILITY (Bác sĩ đi làm khoảng 85%)
        f.write("Avail = [\n")
        for s in range(NUM_SURGEONS):
            row = [1 if random.random() < 0.85 else 0 for _ in range(NUM_DAYS)]
            f.write("  [" + ", ".join(map(str, row)) + "]" + ("," if s < NUM_SURGEONS - 1 else "") + "\n")
        f.write("];\n\n")

        # 5. SKILLS (Phân loại Senior/Junior để logic xếp lịch chặt chẽ hơn)
        # S1-S6: Senior (Làm Main được nhiều loại)
        # S7-S12: Junior (Chủ yếu làm Assist)
        
        f.write("// IsResponsible [Surgeon][Type][Day]\n")
        f.write("IsResponsible = [\n")
        for s in range(NUM_SURGEONS):
            f.write("  [ \n")
            can_main = [0] * 10
            if s < 6: # Senior (S1-S6)
                # Mỗi Senior làm trùm khoảng 4-6 loại phẫu thuật
                my_skills = random.sample(range(10), k=random.randint(4, 6))
                for t_idx in my_skills: can_main[t_idx] = 1
            
            for t in range(10):
                # Skill không đổi theo ngày (copy 5 lần)
                day_skills = [can_main[t]] * NUM_DAYS
                f.write("    [" + ", ".join(map(str, day_skills)) + "]" + ("," if t < 9 else "") + "\n")
            f.write("  ]" + ("," if s < NUM_SURGEONS - 1 else "") + "\n")
        f.write("];\n\n")

        f.write("// IsAssistant1 [Surgeon][Type][Day]\n")
        f.write("IsAssistant1 = [\n")
        for s in range(NUM_SURGEONS):
            f.write("  [ \n")
            # Senior làm phụ ít hơn, Junior làm phụ nhiều hơn
            can_asst = [1] * 10 
            if s < 6: # Senior lười làm phụ
                 # Random bỏ bớt 3-4 loại
                 unskilled = random.sample(range(10), k=4)
                 for t_idx in unskilled: can_asst[t_idx] = 0
            
            for t in range(10):
                day_skills = [can_asst[t]] * NUM_DAYS
                f.write("    [" + ", ".join(map(str, day_skills)) + "]" + ("," if t < 9 else "") + "\n")
            f.write("  ]" + ("," if s < NUM_SURGEONS - 1 else "") + "\n")
        f.write("];\n\n")

        f.write("// IsAssistant2 [Surgeon][Day]\n")
        f.write("IsAssistant2 = [\n")
        for s in range(NUM_SURGEONS):
            # Junior (S7-S12) luôn làm Asst2, Senior (S1-S6) không làm
            if s >= 6: 
                row = [1] * NUM_DAYS
            else: 
                row = [0] * NUM_DAYS
            f.write("  [" + ", ".join(map(str, row)) + "]" + ("," if s < NUM_SURGEONS - 1 else "") + "\n")
        f.write("];\n")

    print(f"Created file: {filename}")
    print(f"Config: {NUM_PATIENTS} Patient, {NUM_SURGEONS} Surgeon, {NUM_ROOMS} Room.")

if __name__ == "__main__":
    generate_medium_dat()