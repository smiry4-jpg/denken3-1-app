import os
import re
import json
import time
import urllib.request
import urllib.parse
import random
import requests
import streamlit as st
import fitz  # PyMuPDF
from google import genai

# ==========================================
# ⚙️ 画面のデザインと設定
# ==========================================
st.set_page_config(page_title="電験三種 過去問クイズ【Ver 3-1】", layout="centered")
st.title("⚡ 電験三種 過去問クイズ【Ver 3-1】")
st.write("過去5年分のすべての問題（問1〜最終問まで）に挑戦できます。")

base_dir = os.path.dirname(__file__) if '__file__' in locals() else '.'
pdf_dir = os.path.join(base_dir, "pdf")
os.makedirs(pdf_dir, exist_ok=True)

YEARS_MAP = {
    "R07k": "令和7年 下期", "R07s": "令和7年 上期",
    "R06k": "令和6年 下期", "R06s": "令和6年 上期",
    "R05k": "令和5年 下期", "R05s": "令和5年 上期",
    "R04k": "令和4年 下期", "R04s": "令和4年 上期",
    "R03": "令和3年", "R02": "令和2年"
}
SUBS_MAP = {"RIROM": "理論", "DENRYOKU": "電力", "KIKAI": "機械", "HOUKI": "法規"}

# ==========================================
# 🌐 Webからの自動ダウンロード機能（年度×科目・完全分離版）
# ==========================================
HOST_NAME = "raw.github" + "usercontent.com"

def load_web_quizzes_by_target(year_code, subject_name):
    # 💡 画面の選択に合わせて、例：「R07k_電力.json」というピンポイントなURLを自動生成します
    url = f"https://{HOST_NAME}/smiry4-jpg/denken3-1-app/main/{year_code}_{subject_name}.json"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # まだGitHub側にその年度・科目のファイルが作られていない場合は空リストを返す
        return []

# ==========================================
# 🤖 PDFからAIが自動生成する関数（元の機能を維持）
# ==========================================
def generate_quiz_from_pdf(selected_year, selected_sub, pdf_path, data_file_path):
    if not os.path.exists(pdf_path):
        st.error(f"❌ PDFファイルが見つかりません: {pdf_path}")
        return False
    try:
        client = genai.Client()
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        
        prompt = f"""
        電験三種の過去問テキストからクイズデータを抽出してください。
        以下のフォーマットのJSON配列のみを出力してください。
        [{{
            "q_num": "問番号",
            "category": "{SUBS_MAP[selected_sub]}",
            "question": "問題文",
            "choices": ["(1)...", "(2)...", "(3)...", "(4)...", "(5)..."],
            "answer": "正解の番号(例:(1))",
            "explanation": "簡単な解説"
        }}]
        テキスト:
        {full_text}
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        quiz_json_text = response.text
        with open(data_file_path, "w", encoding="utf-8") as f:
            f.write(f"QUIZ_DATA = {quiz_json_text}")
        return True
    except Exception as e:
        st.error(f"🤖 AI生成エラー: {e}")
        return False

# ==========================================
# 🎨 画面の選択UIと問題セット処理
# ==========================================
selected_year = st.selectbox("📅 年度を選択してください", list(YEARS_MAP.keys()), format_func=lambda x: YEARS_MAP[x])
selected_sub = st.selectbox("📚 科目を選択してください", list(SUBS_MAP.keys()), format_func=lambda x: SUBS_MAP[x])
is_shuffle = st.checkbox("🔀 出題順をランダムにする")

if st.button("🟢 この条件で問題をセットする"):
    year_name = YEARS_MAP[selected_year]
    sub_name = SUBS_MAP[selected_sub]
    
    # 💡 押された瞬間に、対象のファイルをピンポイントでロードします
    matched_quizzes = load_web_quizzes_by_target(selected_year, sub_name)
    
    if matched_quizzes:
        if is_shuffle:
            random.shuffle(matched_quizzes)
        st.session_state.quiz_list = matched_quizzes
        st.session_state.current_index = 0
        st.success(f"🌐 GitHubから最新の {year_name}・{sub_name} を読み込みました！")
        st.rerun()
    else:
        # GitHubに個別データがない場合は従来のPDF自動生成を試みる
        data_file_path = os.path.join(base_dir, f"quiz_data_{selected_year}_{selected_sub}.py")
        pdf_path = os.path.join(pdf_dir, f"{selected_year}_{selected_sub}.pdf")
        
        if not os.path.exists(data_file_path):
            with st.spinner("⏳ データを全自動構築中..."):
                generate_quiz_from_pdf(selected_year, selected_sub, pdf_path, data_file_path)
        
        if os.path.exists(data_file_path):
            try:
                import sys
                import importlib
                module_name = f"quiz_data_{selected_year}_{selected_sub}"
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                mod = importlib.import_module(module_name)
                quizzes = mod.QUIZ_DATA
                if is_shuffle:
                    random.shuffle(quizzes)
                st.session_state.quiz_list = quizzes
                st.session_state.current_index = 0
                st.success(f"🤖 PDFからデータを構築し、セットしました！")
                st.rerun()
            except Exception as e:
                st.error(f"データの読み込みに失敗しました: {e}")

# ==========================================
# 📝 クイズ出題・回答メイン処理
# ==========================================
if "quiz_list" in st.session_state and st.session_state.quiz_list:
    quizzes = st.session_state.quiz_list
    idx = st.session_state.current_index
    
    if idx < len(quizzes):
        quiz = quizzes[idx]
        st.subheader(f"📝 第 {idx + 1} 問 / 全 {len(quizzes)} 問 (問 {quiz['q_num']})")
        st.markdown(f"**【問題】**\n{quiz['question']}")
        
        if quiz.get("has_image") and quiz.get("image_description"):
            st.caption(f"🔍 [図面解説] {quiz['image_description']}")
            
        with st.form(key=f"quiz_form_{idx}"):
            user_choice = st.radio("正解を選んでください：", quiz["choices"])
            submit = st.form_submit_button(label="回答を確定する")
            
        if submit:
            st.session_state[f"answered_{idx}"] = True
            st.session_state[f"user_choice_{idx}"] = user_choice
            
        if st.session_state.get(f"answered_{idx}"):
            u_choice = st.session_state.get(f"user_choice_{idx}")
            if quiz["answer"] in u_choice:
                st.success("⭕ 正解です！")
            else:
                st.error(f"❌ 不正解... 正解は {quiz['answer']} です。")
                
            st.markdown("### 💡 詳細解説")
            st.info(quiz["explanation"])
            
            search_word = f"電験三種 {YEARS_MAP[selected_year].replace(' ', '')} {SUBS_MAP[selected_sub]} 問{quiz['q_num']}"
            encoded_search_word = urllib.parse.quote(search_word)
            youtube_app_url = f"youtube://results?search_query={encoded_search_word}"
            
            st.markdown(f"🎬 **解説動画へのリンク**")
            st.markdown(f"👉 [🌐 ここをタップして YouTube アプリで直接検索する]({youtube_app_url})")
            
            if st.button("➡️ 次の問題に進む"):
                st.session_state.current_index += 1
                st.rerun()
    else:
        st.balloons()
        st.success("🎉 すべての問題が終了しました！お疲れ様でした。")
        if st.button("🔄 もう一度最初から解く"):
            st.session_state.current_index = 0
            st.rerun()
