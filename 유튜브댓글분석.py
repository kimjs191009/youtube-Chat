import re
import pandas as pd
import streamlit as st
import plotly.express as px

from googleapiclient.discovery import build

st.set_page_config(
    page_title="유튜브 댓글 분석기",
    page_icon="📺",
    layout="wide"
)

# ------------------
# API KEY
# ------------------

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

# ------------------
# 함수
# ------------------

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

    request = youtube.videos().list(
        part="snippet,statistics",
        id=video_id
    )

    response = request.execute()

    if not response["items"]:
        return None

    item = response["items"][0]

    return {
        "title": item["snippet"]["title"],
        "channel": item["snippet"]["channelTitle"],
        "views": int(item["statistics"].get("viewCount", 0)),
        "likes": int(item["statistics"].get("likeCount", 0))
    }


def get_comments(video_id, max_comments=300):

    comments = []
    next_page_token = None

    while len(comments) < max_comments:

        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token,
            textFormat="plainText"
        )

        response = request.execute()

        for item in response["items"]:

            text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]

            comments.append(text)

            if len(comments) >= max_comments:
                break

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return comments


# ------------------
# UI
# ------------------

st.title("📺 YouTube 댓글 분석 대시보드")

st.markdown(
    "유튜브 영상 URL을 입력하면 댓글을 분석합니다."
)

st.sidebar.header("설정")

video_url = st.sidebar.text_input(
    "YouTube 영상 URL"
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
        st.warning("영상 URL을 입력하세요.")
        st.stop()

    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("올바른 유튜브 URL이 아닙니다.")
        st.stop()

    with st.spinner("댓글 수집 중..."):

        info = get_video_info(video_id)

        comments = get_comments(
            video_id,
            comment_count
        )

    if not comments:
        st.error("댓글을 가져오지 못했습니다.")
        st.stop()

    st.success(f"{len(comments)}개 댓글 수집 완료")

    # 영상 정보
    col1, col2, col3 = st.columns(3)

    col1.metric(
        "조회수",
        f"{info['views']:,}"
    )

    col2.metric(
        "좋아요",
        f"{info['likes']:,}"
    )

    col3.metric(
        "댓글 수집",
        f"{len(comments):,}"
    )

    st.subheader("영상 정보")

    st.write(f"제목 : {info['title']}")
    st.write(f"채널 : {info['channel']}")

    # 댓글 데이터
    df = pd.DataFrame({
        "댓글": comments
    })

    st.subheader("댓글 데이터")

    st.dataframe(
        df,
        use_container_width=True
    )

    # 댓글 길이 분석
    df["길이"] = df["댓글"].str.len()

    fig = px.histogram(
        df,
        x="길이",
        title="댓글 길이 분포"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    st.subheader("통계")

    st.write(
        f"평균 댓글 길이 : {df['길이'].mean():.1f}자"
    )

    st.write(
        f"최대 댓글 길이 : {df['길이'].max()}자"
    )

    csv = df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        "CSV 다운로드",
        csv,
        file_name="youtube_comments.csv",
        mime="text/csv"
    )
