import os
import urllib.parse
import streamlit as st

# ==========================================
# 👑 外部のデータ専用部屋（quiz_data.py）からデータをガッチャンコします
# ==========================================
try:
    from quiz_data import ALL_QUIZ_DATA
    QUIZ_DATABASE = ALL_QUIZ_DATA
except Exception as e:
    st.error(f"❌ データ専用ファイル（quiz_data.py）の読み込みに失敗しました。ファイルが作成されているか確認してください。詳細: {str(e)}")
    st.stop()

# ==========================================
# ⚙️ 画面のデザインと設定
# ==========================================
st.set_page_config(page_title="電験三種 過去問クイズ【Ver 3-1】", layout="centered")
st.title("⚡ 電験三種 過去問クイズ【Ver 3-1】")
st.write("過去5年分のすべての問題から、科目別に挑戦できます。")
st.write("🟢 『完全独立・手動蓄積モード』：通信エラーやAIの回数制限は100%発生しません。")

# ==========================================
# 🎮 クイズ画面の制御処理（セッション管理）
# ==========================================
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = 0
    st.session_state.active_quiz = None
    st.session_state.is_answered = False

YEARS_MAP = {
    "R06k": "令和6年 下期", "R06s": "令和6年 上期",
    "R05k": "令和5年 下期", "R05s": "令和5年 上期",
    "R04k": "令和4年 下期", "R04s": "令和4年 上期",
    "R03": "令和3年", "R02": "令和2年"
}
SUBS_MAP = {"RIROM": "理論", "DENRYOKU": "電力", "KIKAI": "機械", "HOUKI": "法規"}

selected_sub = st.selectbox("挑戦する科目を選んでください", list(SUBS_MAP.keys()), format_func=lambda x: SUBS_MAP[x])
selected_year = st.selectbox("年度を選んでください", list(YEARS_MAP.keys()), format_func=lambda x: YEARS_MAP[x])

if st.button("⚡ クイズを開始する", type="primary"):
    db_key = f"{selected_year}_{selected_sub}"
    if db_key in QUIZ_DATABASE:
        st.session_state.active_quiz = QUIZ_DATABASE[db_key]
        st.session_state.current_q_idx = 0
        st.session_state.is_answered = False
        st.success(f"🎯 {YEARS_MAP[selected_year]}の{SUBS_MAP[selected_sub]} を正常にロードしました！")
        st.rerun()
    else:
        st.error(f"⚠️ 【{YEARS_MAP[selected_year]}度 {SUBS_MAP[selected_sub]}】のデータは、まだ保管庫（quiz_data.py）に書き込まれていません。")

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
        
        # 👑 あなたが大成功させた、YouTubeアプリを一撃で自動検索起動させるURLスキーム！
        search_word = f"電験三種 {YEARS_MAP[selected_year].replace(' ', '')} {SUBS_MAP[selected_sub]} 問{quiz['q_num']}"
        encoded_search_word = urllib.parse.quote(search_word)
        youtube_app_url = f"youtube://results?search_query={encoded_search_word}"
        
        st.markdown(f"🎬 **解説動画へのリンク**")
        st.markdown(f"👉 [🌐 ここをタップして YouTube アプリで直接検索する]({youtube_app_url})")
        
        # 🌟【インデント完全修正】「次へ進むボタン」の中身がタップされた瞬間だけ、確実に画面を書き換えるロジックに段落を修正しました
        if idx < len(st.session_state.active_quiz) - 1:
            if st.button("➡️ 次の問題へ"):
                st.session_state.current_q_idx += 1
                st.session_state.is_answered = False
                st.rerun()
        else:
            st.info("🏁 この年度・科目の保管済み問題は以上です！")
