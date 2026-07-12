# app.py
# 【ステップ1】 quiz_data.py のデータを一切壊さずに、100%正しく読み込めるか確認するプログラム
import streamlit as st
import quiz_data

st.title("⚡ 電験3種クイズアプリ（開発画面）")
st.subheader("現在の進捗：【ステップ1】データの保存と読み込み確認")

try:
    # データを読み込み、エラーが起きないかテストする
    all_quizzes = quiz_data.quizzes
    total_count = len(all_quizzes)
    
    # 成功メッセージ
    st.success(f"⭕ quiz_data.py の保存・読み込みに成功しました！")
    st.info(f"現在、合計 {total_count} 問の「科目別・種類別・動画リンク付きデータ」がエラーなく認識されています。")
    
    # 元のデータを壊していないか、画面で確認できるように表示
    st.write("📂 保存されているデータの一覧：")
    st.json(all_quizzes)

except Exception as e:
    st.error("❌ 読み込みに失敗しました。")
    st.write(f"エラーの詳細: {e}")
