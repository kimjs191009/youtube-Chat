```python
import re
from collections import Counter

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns

from googleapiclient.discovery import build
from wordcloud import WordCloud

from konlpy.tag import Okt


# -----------------------------------
# 페이지 설정
# -----------------------------------
st.set_page_config(
    page_title="YouTube 댓글 분석기",
    layout="wide"
)

st.title("📺 YouTube 댓글 분석 웹앱")
st.markdown("유튜브 영상 댓글을 수집하고 분석합니다.")


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
# 유튜브 video_id 추출
# -----------------------------------
def extract_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)

    if match:
        return match.group(1)

    return None


# -----------------------------------
# 댓글 수집 함수
# -----------------------------------
def get_comments(api_key, video_id, max_comments=100):

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

    df = pd.DataFrame(comments)

    return df


# -----------------------------------
# 워드클라우드 생성
# -----------------------------------
def generate_wordcloud(text):

    okt = Okt()

    nouns = okt.nouns(text)

    # 2글자 이상 단어만 사용
    nouns = [word for word in nouns if len(word) > 1]

    counter = Counter(nouns)

    wordcloud = WordCloud(
        font_path="malgun.ttf",  # Windows
        background_color="white",
        width=1200,
        height=600
    ).generate_from_frequencies(counter)

    return wordcloud


# -----------------------------------
# 분석 시작 버튼
# -----------------------------------
if st.button("댓글 분석 시작"):

    if not api_key:
        st.error("API Key를 입력하세요.")
        st.stop()

    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("올바른 유튜브 링크를 입력하세요.")
        st.stop()

    with st.spinner("댓글 수집 중..."):

        df = get_comments(
            api_key,
            video_id,
            max_comments
        )

    st.success(f"{len(df)}개의 댓글 수집 완료!")

    # -----------------------------------
    # 데이터 전처리
    # -----------------------------------
    df["publishedAt"] = pd.to_datetime(df["publishedAt"])

    df["date"] = df["publishedAt"].dt.date
    df["hour"] = df["publishedAt"].dt.hour

    # -----------------------------------
    # 데이터 미리보기
    # -----------------------------------
    st.subheader("📋 댓글 데이터")

    st.dataframe(df)

    # -----------------------------------
    # 시간대별 댓글 추이
    # -----------------------------------
    st.subheader("📈 시간대별 댓글 추이")

    hourly_comments = (
        df.groupby("hour")
        .size()
        .reset_index(name="count")
    )

    fig, ax = plt.subplots(figsize=(12, 5))

    sns.lineplot(
        data=hourly_comments,
        x="hour",
        y="count",
        marker="o",
        ax=ax
    )

    ax.set_xlabel("시간")
    ax.set_ylabel("댓글 수")
    ax.set_title("시간대별 댓글 수")

    st.pyplot(fig)

    # -----------------------------------
    # 좋아요 수 분석
    # -----------------------------------
    st.subheader("👍 댓글 좋아요 분석")

    fig2, ax2 = plt.subplots(figsize=(12, 5))

    sns.histplot(
        df["likeCount"],
        bins=30,
        kde=True,
        ax=ax2
    )

    ax2.set_xlabel("좋아요 수")
    ax2.set_ylabel("빈도")
    ax2.set_title("댓글 좋아요 분포")

    st.pyplot(fig2)

    # 상위 좋아요 댓글
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

    text = " ".join(df["comment"].astype(str))

    try:
        wc = generate_wordcloud(text)

        fig3, ax3 = plt.subplots(figsize=(15, 7))

        ax3.imshow(wc, interpolation="bilinear")
        ax3.axis("off")

        st.pyplot(fig3)

    except Exception as e:
        st.error(f"워드클라우드 생성 실패: {e}")
```
