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
    const container = document.querySelector('.ppt-player-container');
    const layoutButtons = Array.from(document.querySelectorAll('.ppt-layout-btn'));
    let activeSwitcherBtn = document.querySelector('.video-switcher__btn.is-active');
    let activeLayoutBtn = document.querySelector('.ppt-layout-btn.is-active');

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

    // 标记是否在最大化截图模式下手动翻页
    let isManualSlideNavigation = false;

    videoPlayer.addEventListener('timeupdate', () => {
        // 在最大化截图模式下手动翻页时，不自动更新 active 状态
        const currentLayout = container.getAttribute('data-layout') || 'split';
        if (currentLayout === 'timeline-max' && isManualSlideNavigation) {
            return;
        }

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

    // 获取当前激活的截图索引
    const getActiveSlideIndex = () => {
        const activeItem = timeline.querySelector('.ppt-timeline__item.active');
        if (!activeItem) {
            return -1;
        }
        return timelineItems.indexOf(activeItem);
    };

    // 跳转到指定索引的截图
    const jumpToSlide = (index) => {
        if (index < 0 || index >= timelineItems.length) {
            return;
        }
        const item = timelineItems[index];
        const timestamp = parseFloat(item.getAttribute('data-timestamp'));
        if (!Number.isNaN(timestamp)) {
            // 标记为手动翻页，防止 timeupdate 事件干扰
            isManualSlideNavigation = true;
            
            videoPlayer.currentTime = timestamp;
            timelineItems.forEach((i) => i.classList.remove('active'));
            item.classList.add('active');
            // 滚动到可见区域
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            
            // 短暂延迟后恢复自动更新
            setTimeout(() => {
                isManualSlideNavigation = false;
            }, 300);
        }
    };

    document.addEventListener('keydown', (event) => {
        // 获取当前布局模式
        const currentLayout = container.getAttribute('data-layout') || 'split';
        
        // 在最大化截图模式下，键盘控制截图翻页
        if (currentLayout === 'timeline-max') {
            if (event.code === 'Space' && event.target.tagName !== 'INPUT' && event.target.tagName !== 'TEXTAREA') {
                event.preventDefault();
                const currentIndex = getActiveSlideIndex();
                const nextIndex = currentIndex < 0 ? 0 : currentIndex + 1;
                jumpToSlide(nextIndex);
            } else if (event.code === 'ArrowLeft' || event.code === 'ArrowUp') {
                event.preventDefault();
                const currentIndex = getActiveSlideIndex();
                const prevIndex = currentIndex < 0 ? 0 : currentIndex - 1;
                jumpToSlide(prevIndex);
            } else if (event.code === 'ArrowRight' || event.code === 'ArrowDown') {
                event.preventDefault();
                const currentIndex = getActiveSlideIndex();
                const nextIndex = currentIndex < 0 ? 0 : currentIndex + 1;
                jumpToSlide(nextIndex);
            }
        } else {
            // 在视频模式下，键盘控制视频播放
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

    // 布局切换功能
    layoutButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const layout = button.getAttribute('data-layout');
            if (!layout || button === activeLayoutBtn) {
                return;
            }

            container.setAttribute('data-layout', layout);
            
            if (activeLayoutBtn) {
                activeLayoutBtn.classList.remove('is-active');
            }
            button.classList.add('is-active');
            activeLayoutBtn = button;

            // 切换到最大化截图时暂停视频并确保有激活的截图
            if (layout === 'timeline-max') {
                try {
                    videoPlayer.pause();
                } catch (err) {
                    console.warn('[ppt_video_player] 暂停视频失败', err);
                }
                
                // 标记进入手动翻页模式
                isManualSlideNavigation = true;
                
                // 如果没有激活的截图，自动激活第一张或当前视频时间对应的截图
                const currentIndex = getActiveSlideIndex();
                if (currentIndex < 0 && timelineItems.length > 0) {
                    // 根据当前视频时间找到对应的截图
                    const currentTime = videoPlayer.currentTime;
                    let matchIndex = 0;
                    for (let i = timelineItems.length - 1; i >= 0; i -= 1) {
                        const timestamp = parseFloat(timelineItems[i].getAttribute('data-timestamp'));
                        if (!Number.isNaN(timestamp) && currentTime >= timestamp) {
                            matchIndex = i;
                            break;
                        }
                    }
                    timelineItems.forEach((item, idx) => {
                        if (idx === matchIndex) {
                            item.classList.add('active');
                        } else {
                            item.classList.remove('active');
                        }
                    });
                    // 滚动到激活的截图
                    timelineItems[matchIndex].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            } else {
                // 切换到其他模式时，恢复视频时间同步
                isManualSlideNavigation = false;
            }

            // 切换布局后重新同步高度
            setTimeout(applyHeightSync, 50);
        });
    });

    // 默认始终使用左右布局（不恢复上次的布局偏好）
    if (container) {
        container.setAttribute('data-layout', 'split');
        const splitBtn = layoutButtons.find(btn => btn.getAttribute('data-layout') === 'split');
        if (splitBtn) {
            layoutButtons.forEach(btn => btn.classList.remove('is-active'));
            splitBtn.classList.add('is-active');
            activeLayoutBtn = splitBtn;
        }
    }

    applyHeightSync();
    
    // 页面加载后自动播放视频
    videoPlayer.addEventListener('loadedmetadata', () => {
        videoPlayer.play().catch((err) => {
            console.warn('[ppt_video_player] 自动播放被浏览器阻止', err);
        });
    }, { once: true });

    console.log('[ppt_video_player] 初始化完成');
})();

