import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import os
import csv

# --- CẤU HÌNH ---
# Thay vì dùng hộp thoại chọn file, ta điền tên file trực tiếp ở đây.
# Hãy chắc chắn bạn đã UPLOAD file 'gantt.csv' lên cùng thư mục với script này trên Antigravity.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEN_FILE_CSV = os.path.join(SCRIPT_DIR, 'gantt1B.csv')
# ----------------

def ve_bieu_do_gantt_dep():
    # 1. Kiểm tra file
    print(f"[*] Dang tim file '{TEN_FILE_CSV}'...")
    
    if not os.path.exists(TEN_FILE_CSV):
        print(f"[X] LOI: Khong tim thay file '{TEN_FILE_CSV}'.")
        print("[!] Huong dan: Hay upload file gantt.csv vao cung thu muc chay code nay.")
        return

    # 2. Đọc dữ liệu
    try:
        # Tự động phát hiện delimiter (dấu phẩy hoặc dấu chấm phẩy)
        with open(TEN_FILE_CSV, 'r', encoding='utf-8') as f:
            sample = f.read(1024)  # Đọc 1024 ký tự đầu để phát hiện
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
        
        df = pd.read_csv(TEN_FILE_CSV, delimiter=delimiter)
    except Exception as e:
        print(f"[X] Loi doc file: {e}")
        return

    if df.empty:
        print("[!] File CSV rong!")
        return

    print("[OK] Da doc du lieu thanh cong. Dang ve bieu do...")

    # Sắp xếp dữ liệu
    df = df.sort_values(by=['day', 'surgeon', 'start'])

    cac_ngay = sorted(df['day'].unique())
    danh_sach_bac_si = sorted(df['surgeon'].unique(), reverse=True) 
    danh_sach_benh_nhan = df['patient'].unique()

    # Tạo bảng màu
    colors = plt.cm.tab20.colors + plt.cm.tab20b.colors + plt.cm.tab20c.colors
    mau_benh_nhan = {p: colors[i % len(colors)] for i, p in enumerate(danh_sach_benh_nhan)}

    # 3. Vẽ biểu đồ
    fig, axes = plt.subplots(nrows=len(cac_ngay), ncols=1, figsize=(15, 4 * len(cac_ngay)), constrained_layout=True)
    
    if len(cac_ngay) == 1: axes = [axes]

    for i, ngay in enumerate(cac_ngay):
        ax = axes[i]
        data_ngay = df[df['day'] == ngay]
        
        # Tiêu đề
        ax.set_title(f"LICH PHAU THUAT - NGAY {ngay}", fontsize=16, fontweight='bold', color='#1f77b4', loc='left')
        
        # Trục Y
        ax.set_yticks(danh_sach_bac_si)
        ax.set_yticklabels([f"BS {s}" for s in danh_sach_bac_si], fontsize=11, fontweight='bold')
        ax.set_ylabel("Doi ngu Bac si", fontsize=12)

        # Trục X (Giờ)
        gio_bat_dau_lam = 8 
        def format_gio(x, pos):
            gio = int(x // 60) + gio_bat_dau_lam
            phut = int(x % 60)
            return f"{gio}:{phut:02d}"

        ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_gio))
        ax.xaxis.set_major_locator(ticker.MultipleLocator(60))
        
        max_time = data_ngay['finish'].max()
        ax.set_xlim(0, max(480, max_time + 60)) 
        ax.set_xlabel("Thoi gian trong ngay", fontsize=12)

        # Lưới
        ax.grid(True, axis='x', linestyle=':', alpha=0.7, color='gray')
        ax.set_axisbelow(True)

        # Vẽ thanh Gantt
        for _, row in data_ngay.iterrows():
            bs = row['surgeon']
            start = row['start']
            duration = row['duration']
            patient = row['patient']
            
            ax.barh(y=bs, width=duration, left=start, 
                    color=mau_benh_nhan[patient], edgecolor='white', linewidth=1, height=0.7, alpha=0.9)
            
            if duration > 15:
                center_x = start + duration/2
                ax.text(center_x, bs, f"P{patient}", 
                        ha='center', va='center', color='white', fontsize=9, fontweight='bold')

    # 4. Lưu ảnh (Quan trọng với Antigravity)
    ten_file_anh = 'Gantt_Chart_Dep.png'
    plt.savefig(ten_file_anh, dpi=300)
    print(f"[OK] DA VE XONG! Anh duoc luu tai: {ten_file_anh}")
    print("[!] Hay tim file anh nay trong thu muc file cua ban de tai ve hoac xem.")
    
    # Nếu môi trường hỗ trợ hiển thị (như Jupyter), dòng này sẽ hiện ảnh
    # Nếu không, nó sẽ bị bỏ qua mà không gây lỗi
    try:
        plt.show()
    except:
        pass

if __name__ == "__main__":
    ve_bieu_do_gantt_dep()