```python
import re
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

from googleapiclient.discovery import build
from wordcloud import WordCloud
import matplotlib.pyplot as plt


# -----------------------------------
# 페이지 설정
# -----------------------------------
st.set_page_config(
    page_title="YouTube 댓글 분석기",
    layout="wide"
)

st.title("📺 YouTube 댓글 분석 웹앱")
st.markdown("유튜브 댓글 데이터를 수집하고 시각화합니다.")


# -----------------------------------
# 사이드바
# -----------------------------------
st.sidebar.header("설정")

api_key = st.sidebar.text_input(
    "YouTube API Key",
    type="password"
)

video_url = st.sidebar.text_input(
    "YouTube 영상 링크",
    placeholder="https://www.youtube.com/watch?v=..."
)

max_comments = st.sidebar.slider(
    "수집할 댓글 수",
    min_value=20,
    max_value=10000,
    value=200,
    step=20
)


# -----------------------------------
# video_id 추출
# -----------------------------------
def extract_video_id(url):

    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)

        if match:
            return match.group(1)

    return None


# -----------------------------------
# 댓글 수집
# -----------------------------------
def get_comments(api_key, video_id, max_comments):

    youtube = build(
        "youtube",
        "v3",
        developerKey=api_key
    )

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

            snippet = item["snippet"]["topLevelComment"]["snippet"]

            comments.append({
                "author": snippet["authorDisplayName"],
                "comment": snippet["textDisplay"],
                "likeCount": snippet["likeCount"],
                "publishedAt": snippet["publishedAt"]
            })

            if len(comments) >= max_comments:
                break

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return pd.DataFrame(comments)


# -----------------------------------
# 텍스트 정리
# -----------------------------------
def clean_text(text):

    text = re.sub(r"http\\S+", "", text)
    text = re.sub(r"[^가-힣a-zA-Z0-9\\s]", "", text)

    return text.lower()


# -----------------------------------
# 단어 추출
# -----------------------------------
def extract_keywords(text):

    stopwords = {
        "그리고", "하지만", "진짜", "너무", "정말",
        "영상", "댓글", "그냥", "이번", "저는",
        "입니다", "합니다", "있는", "하는", "the",
        "this", "that", "with"
    }

    words = text.split()

    words = [
        word for word in words
        if len(word) >= 2 and word not in stopwords
    ]

    return words


# -----------------------------------
# 워드클라우드 생성
# -----------------------------------
def create_wordcloud(words):

    counter = Counter(words)

    wordcloud = WordCloud(
        font_path=None,
        width=1200,
        height=600,
        background_color="white"
    ).generate_from_frequencies(counter)

    return wordcloud


# -----------------------------------
# 분석 버튼
# -----------------------------------
if st.button("댓글 분석 시작"):

    if not api_key:
        st.error("YouTube API Key를 입력하세요.")
        st.stop()

    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("올바른 유튜브 링크를 입력하세요.")
        st.stop()

    with st.spinner("댓글 수집 중..."):

        try:
            df = get_comments(
                api_key,
                video_id,
                max_comments
            )

        except Exception as e:
            st.error(f"댓글 수집 실패: {e}")
            st.stop()

    if df.empty:
        st.warning("댓글이 없습니다.")
        st.stop()

    st.success(f"{len(df)}개의 댓글 수집 완료!")

    # -----------------------------------
    # 데이터 전처리
    # -----------------------------------
    df["publishedAt"] = pd.to_datetime(df["publishedAt"])

    df["date"] = df["publishedAt"].dt.date
    df["hour"] = df["publishedAt"].dt.hour

    # -----------------------------------
    # KPI
    # -----------------------------------
    col1, col2, col3 = st.columns(3)

    col1.metric("총 댓글 수", len(df))
    col2.metric("평균 좋아요", round(df["likeCount"].mean(), 2))
    col3.metric("최대 좋아요", int(df["likeCount"].max()))

    # -----------------------------------
    # 데이터 보기
    # -----------------------------------
    st.subheader("📋 댓글 데이터")

    st.dataframe(df)

    # CSV 다운로드
    csv = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="CSV 다운로드",
        data=csv,
        file_name="youtube_comments.csv",
        mime="text/csv"
    )

    # -----------------------------------
    # 시간대별 댓글 추이
    # -----------------------------------
    st.subheader("📈 시간대별 댓글 추이")

    hourly = (
        df.groupby("hour")
        .size()
        .reset_index(name="count")
    )

    fig = px.line(
        hourly,
        x="hour",
        y="count",
        markers=True,
        title="시간대별 댓글 수"
    )

    st.plotly_chart(fig, use_container_width=True)

    # -----------------------------------
    # 좋아요 분석
    # -----------------------------------
    st.subheader("👍 댓글 좋아요 분석")

    fig2 = px.histogram(
        df,
        x="likeCount",
        nbins=30,
        title="좋아요 분포"
    )

    st.plotly_chart(fig2, use_container_width=True)

    # -----------------------------------
    # TOP 댓글
    # -----------------------------------
    st.subheader("🔥 좋아요 TOP 댓글")

    top_comments = (
        df.sort_values(
            by="likeCount",
            ascending=False
        )
        [["author", "comment", "likeCount"]]
        .head(10)
    )

    st.dataframe(top_comments)

    # -----------------------------------
    # 워드클라우드
    # -----------------------------------
    st.subheader("☁️ 자주 등장하는 단어")

    all_text = " ".join(
        df["comment"].astype(str)
    )

    cleaned = clean_text(all_text)

    words = extract_keywords(cleaned)

    if len(words) > 0:

        wc = create_wordcloud(words)

        fig3, ax = plt.subplots(figsize=(15, 7))

        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")

        st.pyplot(fig3)

    else:
        st.warning("워드클라우드를 생성할 단어가 부족합니다.")
```
