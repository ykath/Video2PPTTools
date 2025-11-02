/**
 * PPT 视频播放页交互脚本
 * - 支持多视频分段切换
 * - 同步左、右两列高度，右列使用内部滚动
 * - 截图时间轴的跳转与高亮
 */

(function () {
    'use strict';

    const videoPlayer = document.getElementById('ppt-video-player');
    const timeline = document.getElementById('ppt-timeline');

    if (!videoPlayer || !timeline) {
        console.warn('[ppt_video_player] 必要的 DOM 元素缺失，脚本终止');
        return;
    }

    const timelineItems = Array.from(timeline.querySelectorAll('.ppt-timeline__item'));
    const switcherButtons = Array.from(document.querySelectorAll('.video-switcher__btn'));
    const videoSection = document.querySelector('.ppt-player__video-section');
    const timelineSection = document.querySelector('.ppt-player__timeline-section');
    let activeSwitcherBtn = document.querySelector('.video-switcher__btn.is-active');

    const syncSectionHeights = () => {
        if (!videoSection || !timelineSection) {
            return;
        }
        timelineSection.style.height = 'auto';
        const height = videoSection.getBoundingClientRect().height;
        if (height > 0) {
            timelineSection.style.height = `${Math.ceil(height)}px`;
        }
    };

    const initialSrc = videoPlayer.currentSrc || videoPlayer.getAttribute('src') || '';
    if (initialSrc) {
        videoPlayer.dataset.activeSrc = initialSrc;
    }

    const applyHeightSync = () => window.requestAnimationFrame(syncSectionHeights);

    switcherButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const src = button.getAttribute('data-src');
            if (!src) {
                return;
            }

            const absoluteSrc = new URL(src, window.location.origin).href;
            if (button === activeSwitcherBtn && videoPlayer.dataset.activeSrc === absoluteSrc) {
                return;
            }

            const wasPaused = videoPlayer.paused;
            try {
                videoPlayer.pause();
            } catch (err) {
                console.warn('[ppt_video_player] 暂停视频失败', err);
            }

            videoPlayer.setAttribute('src', src);
            videoPlayer.load();
            videoPlayer.currentTime = 0;
            videoPlayer.dataset.activeSrc = absoluteSrc;

            if (!wasPaused) {
                videoPlayer.play().catch(() => {
                    /* 浏览器阻止自动播放时静默忽略 */
                });
            }

            timelineItems.forEach((item) => item.classList.remove('active'));
            if (activeSwitcherBtn) {
                activeSwitcherBtn.classList.remove('is-active');
            }
            button.classList.add('is-active');
            activeSwitcherBtn = button;

            applyHeightSync();
        });
    });

    timelineItems.forEach((item) => {
        item.addEventListener('dblclick', function () {
            const timestamp = parseFloat(this.getAttribute('data-timestamp'));
            if (!Number.isNaN(timestamp)) {
                videoPlayer.currentTime = timestamp;
                videoPlayer.play().catch(() => {});
                timelineItems.forEach((i) => i.classList.remove('active'));
                this.classList.add('active');
                videoPlayer.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });

        item.addEventListener('click', function () {
            timelineItems.forEach((i) => i.classList.remove('active'));
            this.classList.add('active');
        });
    });

    videoPlayer.addEventListener('timeupdate', () => {
        const currentTime = videoPlayer.currentTime;
        let activeItem = null;

        for (let i = timelineItems.length - 1; i >= 0; i -= 1) {
            const timestamp = parseFloat(timelineItems[i].getAttribute('data-timestamp'));
            if (!Number.isNaN(timestamp) && currentTime >= timestamp) {
                activeItem = timelineItems[i];
                break;
            }
        }

        timelineItems.forEach((item) => {
            if (item === activeItem) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.code === 'Space' && event.target.tagName !== 'INPUT' && event.target.tagName !== 'TEXTAREA') {
            event.preventDefault();
            if (videoPlayer.paused) {
                videoPlayer.play().catch(() => {});
            } else {
                videoPlayer.pause();
            }
        }

        if (event.code === 'ArrowLeft') {
            event.preventDefault();
            videoPlayer.currentTime = Math.max(0, videoPlayer.currentTime - 5);
        }
        if (event.code === 'ArrowRight') {
            event.preventDefault();
            videoPlayer.currentTime = Math.min(videoPlayer.duration || 0, videoPlayer.currentTime + 5);
        }
    });

    ['loadedmetadata', 'loadeddata'].forEach((evt) => {
        videoPlayer.addEventListener(evt, applyHeightSync);
    });

    window.addEventListener('resize', applyHeightSync);

    if (window.ResizeObserver && videoSection) {
        const observer = new ResizeObserver(applyHeightSync);
        observer.observe(videoSection);
    }

    applyHeightSync();
    console.log('[ppt_video_player] 初始化完成');
})();

