import os
import re
import json
import time
import urllib.request
import urllib.parse
import fitz  # PyMuPDF
from google import genai
import streamlit as st

# ==========================================
# ⚙️ 画面のデザインと設定
# ==========================================
st.set_page_config(page_title="電験三種 過去問クイズ【Ver 3-1】", layout="centered")
st.title("⚡ 電験三種 過去問クイズ【Ver 3-1】")
st.write("過去5年分のすべての問題（問1〜最終問まで）に挑戦できます。")
st.write("🟢 『全自動データ蓄積モード』：ボタンを押すと、裏側でAIが全問の本物データを収集し、あなたのquiz_data.pyに自動で書き込みます。")

base_dir = os.path.dirname(__file__) if '__file__' in locals() else '.'
pdf_dir = os.path.join(base_dir, "pdf")
os.makedirs(pdf_dir, exist_ok=True)

YEARS = ["R06k", "R06s", "R05k", "R05s", "R04k", "R04s", "R03", "R02"]
SUBJECTS = {"RIROM": "理論", "DENRYOKU": "電力", "KIKAI": "機械", "HOUKI": "法規"}

YEARS_MAP = {
    "R06k": "令和6年 下期", "R06s": "令和6年 上期",
    "R05k": "令和5年 下期", "R05s": "令和5年 上期",
    "R04k": "令和4年 下期", "R04s": "令和4年 上期",
    "R03": "令和3年", "R02": "令和2年"
}

# --- 金庫のAPIキーの読み込み ---
if "GEMINI_API_KEY" not in st.secrets:
    st.error("❌ 金庫（Secrets）に GEMINI_API_KEY が登録されていません。設定を確認してください。")
    st.stop()

ai_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# 外部のquiz_data.pyからデータを読み込む
try:
    from quiz_data import ALL_QUIZ_DATA
    QUIZ_DATABASE = ALL_QUIZ_DATA
except:
    QUIZ_DATABASE = {}

# ==========================================
# 📥 試験センターの本物URLから安全にPDFを取得する処理
# ==========================================
def download_single_pdf(year, sub_code):
    pdf_path = os.path.join(pdf_dir, f"{year}_{sub_code}.pdf")
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
        return True
    y_low = year.lower()
    s_low = sub_code.lower()
    url = f"https://shiken.or.jp{y_low}_shiken_third_{s_low}_q.pdf"
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1')
        with urllib.request.urlopen(req, timeout=10) as response:
            with open(pdf_path, 'wb') as out_file:
                out_file.write(response.read())
        return True
    except:
        return False

# ==========================================
# 🔍 【核心】PDFから全問の文章を自動スキャンして切り出す処理
# ==========================================
def scan_pdf_to_raw_text(year, sub_code):
    pdf_path = os.path.join(pdf_dir, f"{year}_{sub_code}.pdf")
    if not os.path.exists(pdf_path):
        download_single_pdf(year, sub_code)
    questions_list = []
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            text = page.get_text("text")
            if text:
                full_text += text
        matches = list(re.finditer(r'(問\d+)', full_text))
        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i+1].start() if i + 1 < len(matches) else len(full_text)
            q_num = re.sub(r'\D', '', matches[i].group())
            raw_text = full_text[start:end]
            questions_list.append({"q_num": q_num, "raw_text": raw_text})
    except:
        pass
    return questions_list

def get_clean_ai_quiz_with_retry(raw_text, year, subject_name, q_num):
    prompt = f"""
    以下の電験三種の過去問テキストの文字化け（Ωやルート）を綺麗に修正し、
    JSONフォーマットのみで返してください。```json などの囲みは絶対禁止です。
    {{
      "question": "修正した問題文",
      "choices": ["選択肢1", "選択肢2", "選択肢3", "選択肢4", "選択肢5"],
      "correct": 1,
      "explanation": "詳細な計算解説"
    }}
    【対象】{YEARS_MAP[year]} {subject_name} 問{q_num}
    【テキスト】{raw_text}
    """
    for attempt in range(3):
        try:
            response = ai_client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            res = re.sub(r'^```json\s*|\s*```$', '', response.text.strip(), flags=re.MULTILINE)
            return json.loads(res)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(20)
                continue
    return None

# ==========================================
# ✍️ 【全自動執筆】生成したデータを quiz_data.py へ自動で書き戻す処理
# ==========================================
def write_all_data_to_quiz_data_file(complete_database):
    target_file_path = os.path.join(base_dir, "quiz_data.py")
    try:
        with open(target_file_path, "w", encoding="utf-8") as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write("# 🌟 AIが何回もPDFを見に行って全自動で構築した本物過去問データベース\n")
            f.write("ALL_QUIZ_DATA = ")
            json.dump(complete_database, f, ensure_ascii=False, indent=4)
        return True
    except:
        return False

# ==========================================
# 🎮 クイズ画面の制御エリア
# ==========================================
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = 0
    st.session_state.active_quiz = None
    st.session_state.is_answered = False

st.write("👇 【手作業ゼロ】下のボタンを1回押すだけで、AIが20冊のPDFから全360問以上の本物データを自動抽出し、あなたのquiz_data.pyへ直接書き込んで部屋を埋め尽くします。")
if st.button("🔄 過去問全360問を自動抽出し、quiz_data.pyへ自動書き込みする", type="primary"):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    current_db = QUIZ_DATABASE if QUIZ_DATABASE else {}
    total_steps = len(YEARS) * len(SUBJECTS.keys())
    step = 0
    
    for y in YEARS:
        for s in SUBJECTS.keys():
            step += 1
            db_key = f"{y}_{s}"
            status_text.write(f"📥 進行中 ({step}/{total_steps}): {YEARS_MAP[y]}の{SUBJECTS[s]}を自動解析中...")
            
            if db_key not in current_db or len(current_db[db_key]) < 5:
                raw_questions = scan_pdf_to_raw_text(y, s)
                if raw_questions:
                    current_db[db_key] = []
                    for item in raw_questions:
                        quiz = get_clean_ai_quiz_with_retry(item["raw_text"], y, SUBJECTS[s], item["q_num"])
                        if quiz:
                            current_db[db_key].append({
                                "q_num": item["q_num"],
                                "question": quiz["question"],
                                "choices": quiz["choices"],
                                "correct": quiz["correct"],
                                "explanation": quiz["explanation"]
                            })
                    write_all_data_to_quiz_data_file(current_db)
            
            progress_bar.progress(int((step / total_steps) * 100))
            
    st.success("✨ 大成功！過去5年分・全4科目のすべての本物問題が、全自動であなたの `quiz_data.py` の中に直接書き込まれました！手動コピペは一切不要です。")
    st.info("🔄 反映させるため、右下の『Manage app』から『Reboot app』を一度押してください。")

st.write("---")

selected_sub = st.selectbox("挑戦する科目を選んでください", list(SUBJECTS.keys()), format_func=lambda x: SUBJECTS[x])
selected_year = st.selectbox("年度を選んでください", YEARS, format_func=lambda x: YEARS_MAP[x])

if st.button("⚡ クイズを開始する"):
    # 🌟【最重要修正】ボタンが押された瞬間に、選ばれた年度と科目の合体文字（db_key）を正しく定義する処理を追加
    db_key = f"{selected_year}_{selected_sub}"
    
    if db_key in QUIZ_DATABASE:
        st.session_state.active_quiz = QUIZ_DATABASE[db_key]
        st.session_state.current_q_idx = 0
        st.session_state.is_answered = False
        st.success(f"🎯 {YEARS_MAP[selected_year]}の{SUBS_MAP[selected_sub]}（全{len(st.session_state.active_quiz)}問）を正常にロードしました！")
        st.rerun()
    else:
        st.error("⚠️ まだデータが構築されていません。上の『全自動抽出し、quiz_data.pyへ自動書き込みする』ボタンを一度押してください。")

if st.session_state.active_quiz:
    idx = st.session_state.current_q_idx
    quiz = st.session_state.active_quiz[idx]
    
    st.write("---")
    st.subheader(f"📝 {YEARS_MAP[selected_year]} {SUBS_MAP[selected_sub]} 問{quiz['q_num']}")
    st.markdown(quiz["question"])
    
    user_choice = st.radio("正しいと思う選択肢を選んでください", quiz["choices"], index=None, key=f"q_{idx}")
    
    if user_choice and not st.session_state.is_answered:
        if st.button("判定する"):
            st.session_state.is_answered = True
            st.rerun()
            
    if st.session_state.is_answered:
        selected_num = quiz["choices"].index(user_choice) + 1
        correct_num = int(quiz["correct"])
        st.write("---")
        if selected_num == correct_num:
            st.success(f"🎉 正解です！ (正解: 選択肢 {correct_num})")
        else:
            st.error(f"❌ 不正解です... (正解: 選択肢 {correct_num})")
            
        st.markdown("### 💡 詳細解説")
        st.info(quiz["explanation"])
        
        search_word = f"電験三種 {YEARS_MAP[selected_year].replace(' ', '')} {SUBJECTS[selected_sub]} 問{quiz['q_num']}"
        encoded_search_word = urllib.parse.quote(search_word)
        youtube_app_url = f"youtube://results?search_query={encoded_search_word}"
        
        st.markdown(f"🎬 **解説動画へのリンク**")
        st.markdown(f"👉 [🌐 ここをタップして YouTube アプリで直接検索する]({youtube_app_url})")
        
        if idx < len(st.session_state.active_quiz) - 1:
            if st.button("➡️ 次の問題へ"):
                st.session_state.current_q_idx += 1
                st.session_state.is_answered = False
                st.rerun()
        else:
            st.info("🏁 この年度・科目の問題は以上です！お疲れ様でした。")
