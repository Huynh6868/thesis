def find_preemptable_surgeries(env, required_surgeons, required_room, duration, scheduled_surgeries):
    """
    Tìm các ca elective có thể bị dời để nhường chỗ cho urgent.
    
    Tiêu chí:
    - Status == "scheduled" (chưa bắt đầu thực hiện)
    - Sử dụng một trong các bác sĩ cần thiết HOẶC phòng cần thiết
    - Thời gian lên lịch chồng lấn với [env.now, env.now + duration]
    
    Returns: Danh sách surgeries sắp theo thời gian bắt đầu (muộn nhất trước)
    """
    preemptable = []
    urgent_start = env.now
    urgent_end = env.now + duration
    
    for pid, surgery in scheduled_surgeries.items():
        if surgery["status"] != "scheduled":
            continue
            
        surgery_start = surgery["scheduled_time"]
        surgery_end = surgery_start + surgery["duration"]
        
        # Kiểm tra thời gian có chồng lấn không
        if surgery_start >= urgent_end or surgery_end <= urgent_start:
            continue  # Không chồng lấn
            
        # Kiểm tra có dùng chung resource không
        team = surgery.get("team", {})
        surgeons_used = {team.get("main"), team.get("assist1"), team.get("assist2")} - {None}
        room_used = surgery.get("room")
        
        if surgeons_used & required_surgeons or room_used == required_room:
            preemptable.append(surgery)
    
    # Sắp xếp theo thời gian bắt đầu muộn nhất trước (dời ca muộn trước)
    preemptable.sort(key=lambda x: x["scheduled_time"], reverse=True)
    return preemptable


def find_earliest_slot(env, surgery_type, duration, start_search_time, end_search_time, 
                       surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries):
    """
    Tìm slot sớm nhất để xếp lịch một ca mổ.
    
    Returns: (slot_time, room_number, team) hoặc None nếu không tìm được
    """
    current_time = start_search_time
    
    # Lấy danh sách bác sĩ có skill phù hợp
    mains, assists = eligible_sets(surgery_type, surgeons_meta)
    if not mains or not assists:
        return None
    
    assist2_pool = [f"S{i}" for i in range(7, 11)]
    
    # Thử từng phút cho đến end_search_time
    while current_time <= end_search_time - duration:
        if not is_work_time(current_time):
            current_time += 1
            continue
            
        # Thử tìm team + room rảnh tại thời điểm này
        for main in mains:
            if not is_available_at_time(main, current_time, duration, surgeons_meta, scheduled_surgeries):
                continue
                
            for a1 in assists:
                if a1 == main:
                    continue
                if not is_available_at_time(a1, current_time, duration, surgeons_meta, scheduled_surgeries):
                    continue
                    
                for a2 in assist2_pool:
                    if a2 in {main, a1}:
                        continue
                    if not is_available_at_time(a2, current_time, duration, surgeons_meta, scheduled_surgeries):
                        continue
                        
                    # Tìm được team, giờ tìm phòng
                    for room_num in room_resources.keys():
                        if is_room_available_at_time(room_num, current_time, duration, scheduled_surgeries):
                            return (current_time, room_num, {"main": main, "assist1": a1, "assist2": a2})
        
        current_time += 1
    
    return None


def is_available_at_time(surgeon, start_time, duration, surgeons_meta, scheduled_surgeries):
    """Kiểm tra bác sĩ có rảnh trong khoảng [start_time, start_time + duration] không"""
    end_time = start_time + duration
    
    # Kiểm tra ca làm việc
    if not in_shift(surgeons_meta[surgeon], start_time, duration):
        return False
    
    # Kiểm tra có ca nào đã lên lịch chồng lấn không
    for surgery in scheduled_surgeries.values():
        if surgery["status"] not in ["scheduled", "executing"]:
            continue
            
        team = surgery.get("team", {})
        if surgeon not in {team.get("main"), team.get("assist1"), team.get("assist2")}:
            continue
            
        surgery_start = surgery["scheduled_time"]
        surgery_end = surgery_start + surgery["duration"]
        
        # Kiểm tra chồng lấn
        if not (end_time <= surgery_start or start_time >= surgery_end):
            return False
    
    return True


def is_room_available_at_time(room_num, start_time, duration, scheduled_surgeries):
    """Kiểm tra phòng có rảnh trong khoảng [start_time, start_time + duration] không"""
    end_time = start_time + duration
    
    for surgery in scheduled_surgeries.values():
        if surgery["status"] not in ["scheduled", "executing"]:
            continue
            
        if surgery.get("room") != room_num:
            continue
            
        surgery_start = surgery["scheduled_time"]
        surgery_end = surgery_start + surgery["duration"]
        
        # Kiểm tra chồng lấn
        if not (end_time <= surgery_start or start_time >= surgery_end):
            return False
    
    return True


def reschedule_surgery(env, surgery, scheduled_surgeries, surgeons_meta, surgeon_resources, room_resources, stats):
    """
    Cố gắng xếp lại lịch cho ca mổ bị dời.
    
    Thứ tự ưu tiên:
    1. Cuối ngày hiện tại
    2. Ngày tiếp theo (tìm slot sớm nhất)
    
    Returns: True nếu xếp lại thành công, False nếu delay
    """
    surgery_type = surgery["surgery_type"]
    duration = surgery["duration"]
    pid = surgery["pid"]
    original_time = surgery["scheduled_time"]
    
    # Tính ngày hiện tại
    current_day = int(env.now // MINUTES_PER_DAY)
    end_of_today = (current_day + 1) * MINUTES_PER_DAY - (24 - SHIFT_END_HOUR) * 60
    
    # Thử 1: Cuối ngày hôm nay
    result = find_earliest_slot(env, surgery_type, duration, env.now, end_of_today,
                               surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries)
    
    if result:
        new_time, new_room, new_team = result
        surgery["scheduled_time"] = new_time
        surgery["room"] = new_room
        surgery["team"] = new_team
        surgery["status"] = "scheduled"
        
        stats["preempted_electives"].append({
            "pid": pid,
            "original_time": original_time,
            "new_time": new_time,
            "reason": "Preempted by urgent patient, rescheduled same day"
        })
        return True
    
    # Thử 2: Ngày tiếp theo
    next_day_start = (current_day + 1) * MINUTES_PER_DAY + SHIFT_START_HOUR * 60
    next_day_end = (current_day + 1) * MINUTES_PER_DAY + SHIFT_END_HOUR * 60
    
    if next_day_start < SIM_DURATION:
        result = find_earliest_slot(env, surgery_type, duration, next_day_start, next_day_end,
                                   surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries)
        
        if result:
            new_time, new_room, new_team = result
            surgery["scheduled_time"] = new_time
            surgery["room"] = new_room
            surgery["team"] = new_team
            surgery["status"] = "scheduled"
            
            stats["preempted_electives"].append({
                "pid": pid,
                "original_time": original_time,
                "new_time": new_time,
                "reason": "Preempted by urgent patient, rescheduled next day"
            })
            return True
    
    # Không xếp được lại -> delay
    surgery["status"] = "delayed"
    stats["delayed_elective_patients"].append({
        "patient": pid,
        "surgery_type": surgery_type,
        "scheduled_time": original_time,
        "reason": "Preempted by urgent and cannot reschedule"
    })
    return False
