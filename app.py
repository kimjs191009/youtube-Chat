import re
from collections import Counter

import pandas as pd
import streamlit as st
import plotly.express as px
import matplotlib.pyplot as plt

from googleapiclient.discovery import build
from wordcloud import WordCloud


# =========================
# 기본 설정
# =========================
st.set_page_config(page_title="YouTube 댓글 분석 대시보드", layout="wide")

st.title("📺 YouTube 댓글 분석 대시보드")
st.write("유튜브 영상 댓글을 수집하고 분석합니다")


# =========================
# 사이드바
# =========================
st.sidebar.header("설정")

api_key = st.sidebar.text_input("YouTube API Key", type="password")

video_url = st.sidebar.text_input(
    "YouTube 영상 URL",
    placeholder="https://www.youtube.com/watch?v=..."
)

max_comments = st.sidebar.slider(
    "수집할 댓글 수",
    20, 10000, 300, 20
)


# =========================
# 영상 ID 추출
# =========================
def extract_video_id(url):
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})"
    ]

    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)

    return None


# =========================
# 댓글 수집
# =========================
def get_comments(api_key, video_id, max_comments):
    youtube = build("youtube", "v3", developerKey=api_key)

    comments = []
    next_page_token = None

    while len(comments) < max_comments:

        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token,
            textFormat="plainText",
            order="time"
        )

        response = request.execute()

        for item in response["items"]:
            c = item["snippet"]["topLevelComment"]["snippet"]

            comments.append({
                "author": c["authorDisplayName"],
                "comment": c["textDisplay"],
                "likeCount": c["likeCount"],
                "publishedAt": c["publishedAt"]
            })

            if len(comments) >= max_comments:
                break

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return pd.DataFrame(comments)


# =========================
# 텍스트 정리
# =========================
def clean_text(text):
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^가-힣a-zA-Z0-9\s]", "", text)
    return text


# =========================
# 워드클라우드
# =========================
def create_wordcloud(text):

    font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

    wc = WordCloud(
        font_path=font_path,
        width=1200,
        height=600,
        background_color="white"
    ).generate(text)

    return wc


# =========================
# 실행
# =========================
if st.button("📊 분석 시작"):

    if not api_key:
        st.error("API Key를 입력하세요")
        st.stop()

    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("유튜브 URL이 올바르지 않습니다")
        st.stop()

    with st.spinner("댓글 수집 중..."):
        df = get_comments(api_key, video_id, max_comments)

    if df.empty:
        st.warning("댓글이 없습니다")
        st.stop()

    st.success(f"{len(df)}개 댓글 수집 완료")


    # =========================
    # 전처리
    # =========================
    df["publishedAt"] = pd.to_datetime(df["publishedAt"])
    df["hour"] = df["publishedAt"].dt.hour


    # =========================
    # KPI
    # =========================
    st.subheader("📌 핵심 지표")

    col1, col2, col3 = st.columns(3)

    col1.metric("총 댓글 수", len(df))
    col2.metric("평균 좋아요", round(df["likeCount"].mean(), 2))
    col3.metric("최대 좋아요", int(df["likeCount"].max()))


    # =========================
    # 데이터
    # =========================
    st.subheader("📄 댓글 데이터")
    st.dataframe(df)

    st.download_button(
        "CSV 다운로드",
        df.to_csv(index=False).encode("utf-8-sig"),
        "comments.csv",
        "text/csv"
    )


    # =========================
    # 시간대 분석
    # =========================
    st.subheader("⏰ 시간대별 댓글 수")

    hourly = df.groupby("hour").size().reset_index(name="count")

    fig1 = px.line(
        hourly,
        x="hour",
        y="count",
        markers=True,
        title="시간대별 댓글 추이"
    )

    st.plotly_chart(fig1, use_container_width=True)


    # =========================
    # 좋아요 분석
    # =========================
    st.subheader("👍 좋아요 분포")

    fig2 = px.histogram(
        df,
        x="likeCount",
        nbins=30,
        title="댓글 좋아요 분포"
    )

    st.plotly_chart(fig2, use_container_width=True)


    # =========================
    # TOP 댓글
    # =========================
    st.subheader("🔥 좋아요 TOP 댓글")

    top = df.sort_values("likeCount", ascending=False).head(10)
    st.dataframe(top[["author", "comment", "likeCount"]])


    # =========================
    # 워드클라우드
    # =========================
    st.subheader("☁️ 워드클라우드")

    text = " ".join(df["comment"].astype(str))
    text = clean_text(text)

    wc = create_wordcloud(text)

    fig3, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")

    st.pyplot(fig3)
