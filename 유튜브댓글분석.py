import re
from collections import Counter

import pandas as pd
import streamlit as st
import plotly.express as px
import matplotlib.pyplot as plt

from googleapiclient.discovery import build
from wordcloud import WordCloud

# ----------------------------------
# 페이지 설정
# ----------------------------------

st.set_page_config(
    page_title="유튜브 댓글 분석기",
    page_icon="📺",
    layout="wide"
)

# ----------------------------------
# API KEY
# ----------------------------------

try:
    API_KEY = st.secrets["YOUTUBE_API_KEY"]
except KeyError:
    st.error("Secrets에 YOUTUBE_API_KEY가 없습니다.")
    st.stop()

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)

# ----------------------------------
# 함수
# ----------------------------------

def extract_video_id(url):

    patterns = [
        r"v=([^&]+)",
        r"youtu\.be/([^?]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)

        if match:
            return match.group(1)

    return None


def get_video_info(video_id):

    response = youtube.videos().list(
        part="snippet,statistics",
        id=video_id
    ).execute()

    if not response["items"]:
        return None

    item = response["items"][0]

    return {
        "title": item["snippet"]["title"],
        "channel": item["snippet"]["channelTitle"],
        "views": int(item["statistics"].get("viewCount", 0)),
        "likes": int(item["statistics"].get("likeCount", 0))
    }


def get_comments(video_id, limit):

    comments = []

    next_page_token = None

    while len(comments) < limit:

        response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token,
            textFormat="plainText"
        ).execute()

        for item in response["items"]:

            comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]

            comments.append(comment)

            if len(comments) >= limit:
                break

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return comments


# ----------------------------------
# 화면
# ----------------------------------

st.title("📺 유튜브 댓글 분석 대시보드")

st.write(
    "유튜브 영상 URL을 입력하면 댓글을 수집하고 분석합니다."
)

st.sidebar.header("설정")

video_url = st.sidebar.text_input(
    "YouTube 영상 URL",
    placeholder="https://www.youtube.com/watch?v=..."
)

comment_count = st.sidebar.slider(
    "수집할 댓글 수",
    100,
    1000,
    300,
    100
)

if st.button("📊 분석 시작"):

    if not video_url:
        st.warning("영상 URL을 입력해주세요.")
        st.stop()

    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("유효한 유튜브 URL이 아닙니다.")
        st.stop()

    with st.spinner("댓글 수집 중..."):

        info = get_video_info(video_id)

        comments = get_comments(
            video_id,
            comment_count
        )

    if not comments:
        st.error("댓글을 가져올 수 없습니다.")
        st.stop()

    # ------------------------------
    # 영상 정보
    # ------------------------------

    st.success(
        f"{len(comments)}개 댓글 수집 완료"
    )

    st.subheader("📹 영상 정보")

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "조회수",
        f"{info['views']:,}"
    )

    c2.metric(
        "좋아요",
        f"{info['likes']:,}"
    )

    c3.metric(
        "댓글 수",
        f"{len(comments):,}"
    )

    st.write(f"제목 : {info['title']}")
    st.write(f"채널 : {info['channel']}")

    # ------------------------------
    # 댓글 데이터
    # ------------------------------

    df = pd.DataFrame({
        "댓글": comments
    })

    st.subheader("💬 댓글 목록")

    st.dataframe(
        df,
        use_container_width=True
    )

    # ------------------------------
    # 댓글 길이 분석
    # ------------------------------

    df["길이"] = df["댓글"].str.len()

    st.subheader("📈 댓글 길이 분포")

    fig = px.histogram(
        df,
        x="길이",
        title="댓글 길이 분포"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    st.info(
        f"평균 댓글 길이 : {df['길이'].mean():.1f}자"
    )

    # ------------------------------
    # 단어 분석
    # ------------------------------

    text = " ".join(comments)

    words = re.findall(
        r"[가-힣A-Za-z]{2,}",
        text
    )

    stop_words = {
        "진짜","정말","너무","그냥",
        "근데","이거","저거",
        "합니다","입니다",
        "있는","하는",
        "그리고","에서",
        "유튜브","영상"
    }

    words = [
        w for w in words
        if w not in stop_words
    ]

    # ------------------------------
    # 워드클라우드
    # ------------------------------

    st.subheader("☁️ 워드클라우드")

    if len(words) > 0:

        try:

            wordcloud = WordCloud(
                font_path="fonts/NanumGothic.ttf",
                width=1400,
                height=700,
                background_color="white"
            ).generate(
                " ".join(words)
            )

            fig_wc, ax = plt.subplots(
                figsize=(15, 8)
            )

            ax.imshow(
                wordcloud,
                interpolation="bilinear"
            )

            ax.axis("off")

            st.pyplot(fig_wc)

        except Exception as e:

            st.error(
                f"NanumGothic.ttf 폰트를 찾을 수 없습니다.\n{e}"
            )

    # ------------------------------
    # TOP20 단어
    # ------------------------------

    st.subheader("🔥 자주 등장한 단어 TOP20")

    word_count = Counter(words)

    top_words = word_count.most_common(20)

    top_df = pd.DataFrame(
        top_words,
        columns=["단어", "횟수"]
    )

    st.dataframe(
        top_df,
        use_container_width=True
    )

    fig_words = px.bar(
        top_df,
        x="단어",
        y="횟수",
        title="단어 빈도 TOP20"
    )

    st.plotly_chart(
        fig_words,
        use_container_width=True
    )

    # ------------------------------
    # CSV 다운로드
    # ------------------------------

    st.subheader("📥 CSV 다운로드")

    csv = df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        label="댓글 CSV 다운로드",
        data=csv,
        file_name="youtube_comments.csv",
        mime="text/csv"
    )
