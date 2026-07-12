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
st.write("過去5年分のすべての問題（問1〜最終問まで）に挑戦できます。解いた問題は自動で100%本物データとして蓄積されます。")
st.write("🟢 『クラウドデータ自動蓄積モード』：解けば解くほど、あなただけの完全な本物データベースに育ちます。")

base_dir = os.path.dirname(__file__) if '__file__' in locals() else '.'
pdf_dir = os.path.join(base_dir, "pdf")
db_dir = os.path.join(base_dir, "quiz_db")

os.makedirs(pdf_dir, exist_ok=True)
os.makedirs(db_dir, exist_ok=True)

YEARS = ["R06k", "R06s", "R05k", "R05s", "R04k", "R04s", "R03", "R02"]
SUBJECTS = {"RIROM": "理論", "DENRYOKU": "電力", "KIKAI": "機械", "HOUKI": "法規"}

YEARS_MAP = {
    "R06k": "令和6年 下期", "R06s": "令和6年 上期",
    "R05k": "令和5年 下期", "R05s": "令和5年 上期",
    "R04k": "令和4年 下期", "R04s": "令和4年 上期",
    "R03": "令和3年", "R02": "令和2年"
}

if "GEMINI_API_KEY" not in st.secrets:
    st.error("❌ 金庫（Secrets）に GEMINI_API_KEY が登録されていません。設定を確認してください。")
    st.stop()

ai_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def download_single_pdf(year, sub_code):
    url = f"https://shiken.or.jp{year}_shiken_third_{sub_code}_q.pdf"
    pdf_path = os.path.join(pdf_dir, f"{year}_{sub_code}.pdf")
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
        return True
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1')
        with urllib.request.urlopen(req, timeout=10) as response:
            with open(pdf_path, 'wb') as out_file:
                out_file.write(response.read())
        return True
    except:
        return False

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
    以下の電験三種の過去問テキストの文字化け（Ωやルート）を前後の文脈から綺麗に修正し、
    問題文、選択肢、正解、解説に分解して、以下のJSONフォーマットのみで返してください。囲みは絶対禁止です。
    {{
      "question": "修正した問題文",
      "choices": ["選択肢1の文章", "選択肢2の文章", "選択肢3の文章", "選択肢4の文章", "選択肢5の文章"],
      "correct": 1,
      "explanation": "ステップバイステップの詳細な解説"
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

def load_or_build_real_quiz_database(year, sub_code):
    storage_path = os.path.join(db_dir, f"{year}_{sub_code}_all.json")
    if os.path.exists(storage_path):
        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    raw_questions = scan_pdf_to_raw_text(year, sub_code)
    if not raw_questions:
        return []
    complete_quiz_list = []
    with st.spinner(f"🤖 初回のみ：{YEARS_MAP[year]}の全問題を本物データに変換・蓄積中..."):
        for item in raw_questions:
            quiz = get_clean_ai_quiz_with_retry(item["raw_text"], year, SUBJECTS[sub_code], item["q_num"])
            if quiz:
                complete_quiz_list.append({
                    "q_num": item["q_num"],
                    "question": quiz["question"],
                    "choices": quiz["choices"],
                    "correct": quiz["correct"],
                    "explanation": quiz["explanation"]
                })
    if complete_quiz_list:
        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(complete_quiz_list, f, ensure_ascii=False, indent=2)
    return complete_quiz_list

if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = 0
    st.session_state.active_quiz = None
    st.session_state.is_answered = False

st.write("🔻 最初に1回だけ下のボタンを押すと、過去5年分の全PDFデータ（20個）を自動収集してベースを構築します。")
if st.button("🔄 過去問データを一括同期・保存する", type="primary"):
    with st.spinner("📥 サーバーから全 20 個の PDF を取得中..."):
        success_count = 0
        for y in YEARS:
            for s in SUBJECTS.keys():
                if download_single_pdf(y, s):
                    success_count += 1
        st.success(f"✨ 同期完了！ {success_count} 個のすべての PDF ファイルをクラウド保管庫に保存しました。")

st.write("---")

selected_sub = st.selectbox("挑戦する科目を選んでください", list(SUBJECTS.keys()), format_func=lambda x: SUBJECTS[x])
selected_year = st.selectbox("年度を選んでください", YEARS, format_func=lambda x: YEARS_MAP[x])

if st.button("⚡ クイズを開始する"):
    with st.spinner("📥 本物の過去問データを読み込み中..."):
        data = load_or_build_real_quiz_database(selected_year, selected_sub)
        if data:
            st.session_state.active_quiz = data
            st.session_state.current_q_idx = 0
            st.session_state.is_answered = False
            st.success(f"🎯 {YEARS_MAP[selected_year]}の{SUBS_MAP[selected_sub]}（全{len(data)}問）を正常にロードしました！")
            st.rerun()
        else:
            st.error("⚠️ データの取得に失敗しました。一番上の『一括同期』ボタンを押してから、もう一度お試しください。")

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
