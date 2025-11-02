(function () {
    const WAITING_MESSAGE = "Loading job queue...";
    const REFRESH_INTERVAL = 20000;

    const escapeHtml = (value) => {
        if (value === null || value === undefined) {
            return "";
        }
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    };

    const formatDateTime = (value) => {
        if (!value) {
            return "-";
        }
        const date = value instanceof Date ? value : new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "-";
        }
        return date.toLocaleString();
    };

    const formatStatus = (status) => {
        switch ((status || "").toLowerCase()) {
            case "pending":
                return { text: "Pending", cls: "status-pending" };
            case "running":
                return { text: "Running", cls: "status-running" };
            case "completed":
                return { text: "Completed", cls: "status-completed" };
            case "failed":
                return { text: "Failed", cls: "status-failed" };
            default:
                return { text: status || "Unknown", cls: "status-unknown" };
        }
    };

    document.addEventListener("DOMContentLoaded", () => {
        const config = window.VideoToPPTConfig;
        if (!config || !config.endpoints) {
            console.error("[video_to_ppt] Missing configuration object", config);
            return;
        }

        const form = document.getElementById("ppt-job-form");
        const statusLabel = document.getElementById("form-status");
        const jobsContainer = document.getElementById("jobs-table-container");
        const refreshBtn = document.getElementById("refresh-jobs");
        const autoRefreshToggle = document.getElementById("auto-refresh");
        const detailPlaceholder = document.getElementById("detail-placeholder");
        const detailContainer = document.getElementById("job-detail");
        const submitButton = document.getElementById("ppt-job-submit");
        const processQueueBtn = document.getElementById("process-queue");

        if (
            !form ||
            !statusLabel ||
            !jobsContainer ||
            !refreshBtn ||
            !autoRefreshToggle ||
            !detailPlaceholder ||
            !detailContainer ||
            !submitButton ||
            !processQueueBtn
        ) {
            console.error("[video_to_ppt] Missing required DOM nodes", {
                form,
                statusLabel,
                jobsContainer,
                refreshBtn,
                autoRefreshToggle,
                detailPlaceholder,
                detailContainer,
                submitButton,
                processQueueBtn,
            });
            return;
        }

        form.setAttribute("data-handler", "video_to_ppt");
        form.setAttribute("autocomplete", "off");
        form.setAttribute("novalidate", "novalidate");
        form.setAttribute("action", "javascript:void(0)");
        form.setAttribute("method", "post");
        submitButton.setAttribute("type", "submit");

        statusLabel.textContent = "Script initialised. You can submit jobs now.";
        console.info("[video_to_ppt] script initialised");

        let currentJobId = null;
        let autoRefreshTimer = null;

        const buildDetailHtml = (job) => {
            const statusInfo = formatStatus(job.status);
            const detailRows = [
                { label: "Job ID", value: escapeHtml(job.job_id) },
                {
                    label: "Video URL",
                    value: job.url
                        ? `<a href="${escapeHtml(job.url)}" target="_blank" rel="noopener">${escapeHtml(job.url)}</a>`
                        : "-",
                },
                {
                    label: "Status",
                    value: `<span class="status-badge ${statusInfo.cls}">${statusInfo.text}</span>`,
                },
                { label: "Created", value: formatDateTime(job.created_at) },
                { label: "Started", value: formatDateTime(job.started_at) },
                { label: "Completed", value: formatDateTime(job.completed_at) },
                { label: "Slides", value: job.slide_count != null ? job.slide_count : "-" },
                {
                    label: "PPT Path",
                    value: job.ppt_path ? `<code>${escapeHtml(job.ppt_path)}</code>` : "-",
                },
                {
                    label: "Job Directory",
                    value: job.job_dir ? `<code>${escapeHtml(job.job_dir)}</code>` : "-",
                },
                {
                    label: "Screenshot Dir",
                    value: job.screenshots_dir ? `<code>${escapeHtml(job.screenshots_dir)}</code>` : "-",
                },
                {
                    label: "Threshold",
                    value: job.similarity_threshold ?? "-",
                },
                {
                    label: "Min Interval (s)",
                    value: job.min_interval_seconds ?? "-",
                },
                {
                    label: "Skip First (s)",
                    value: job.skip_first_seconds ?? "-",
                },
                {
                    label: "Image Format",
                    value: job.image_format || "-",
                },
                {
                    label: "Image Quality",
                    value: job.image_quality ?? "-",
                },
                {
                    label: "Fill Mode",
                    value: job.fill_mode ? "Yes" : "No",
                },
            ];

            const detailList = detailRows
                .map(
                    (row) => `
                        <dt>${row.label}</dt>
                        <dd>${row.value || "-"}</dd>
                    `.trim()
                )
                .join("");

            const extraArgs =
                job.extra_download_args && job.extra_download_args.length
                    ? `<details><summary>Extra BBDown arguments</summary><pre>${escapeHtml(
                          job.extra_download_args.join("\n")
                      )}</pre></details>`
                    : "";

            const commandBlock =
                job.command && job.command.length
                    ? `<details><summary>Executed command</summary><pre>${escapeHtml(
                          job.command.join(" ")
                      )}</pre></details>`
                    : "";

            const stdoutBlock = job.stdout
                ? `<details><summary>stdout</summary><pre>${escapeHtml(job.stdout)}</pre></details>`
                : "";

            const stderrBlock = job.stderr
                ? `<details class="text-error"><summary>stderr</summary><pre>${escapeHtml(job.stderr)}</pre></details>`
                : "";

            const errorMessage = job.error_message
                ? `<p class="text-error">Error: ${escapeHtml(job.error_message)}</p>`
                : "";

            return `
                <dl class="detail-grid">
                    ${detailList}
                </dl>
                ${errorMessage}
                ${extraArgs}
                ${commandBlock}
                ${stdoutBlock}
                ${stderrBlock}
            `.trim();
        };

        const renderJobs = (jobs) => {
            if (!jobs || jobs.length === 0) {
                jobsContainer.innerHTML = "<p>No jobs yet. Submit a video to start processing.</p>";
                return;
            }

            const rows = jobs
                .map((job) => {
                    const statusInfo = formatStatus(job.status);
                    const selectedClass = job.job_id === currentJobId ? "selected" : "";
                    return `
                        <tr data-job-id="${escapeHtml(job.job_id)}" class="${selectedClass}">
                            <td class="mono">${escapeHtml(job.job_id)}</td>
                            <td class="title">${escapeHtml(job.title || "(untitled)")}</td>
                            <td>${escapeHtml(job.subtitle || "-")}</td>
                            <td><span class="status-badge ${statusInfo.cls}">${statusInfo.text}</span></td>
                            <td>${job.slide_count != null ? job.slide_count : "-"}</td>
                            <td>${formatDateTime(job.created_at)}</td>
                            <td>${formatDateTime(job.completed_at)}</td>
                            <td>
                                <button type="button" class="btn small" data-action="view" data-job-id="${escapeHtml(
                                    job.job_id
                                )}">详情</button>
                                ${
                                    job.status === "completed"
                                        ? `<a href="${config.frontend.play.replace(
                                              "{job_id}",
                                              encodeURIComponent(job.job_id)
                                          )}" class="btn small" target="_blank" rel="noopener">播放</a>
                                           <a href="${config.endpoints.download.replace(
                                              "{job_id}",
                                              encodeURIComponent(job.job_id)
                                          )}" class="btn small" download>下载PPT</a>`
                                        : ""
                                }
                                ${
                                    job.status === "failed" || job.status === "completed"
                                        ? `<button type="button" class="btn small" data-action="reprocess" data-job-id="${escapeHtml(
                                              job.job_id
                                          )}">重新处理</button>`
                                        : ""
                                }
                            </td>
                        </tr>
                    `.trim();
                })
                .join("");

            jobsContainer.innerHTML = `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Job ID</th>
                            <th>Title</th>
                            <th>Subtitle</th>
                            <th>Status</th>
                            <th>Slides</th>
                            <th>Created</th>
                            <th>Completed</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                <p class="muted">Total ${jobs.length} record(s).</p>
            `.trim();
        };

        const loadJobs = async () => {
            try {
                const response = await fetch(config.endpoints.list);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = await response.json();
                renderJobs(data.items || []);
            } catch (error) {
                console.error("[video_to_ppt] Failed to load jobs", error);
                jobsContainer.innerHTML = `<p class="text-error">Failed to load jobs: ${escapeHtml(
                    error.message
                )}</p>`;
            }
        };

        const loadJobDetail = async (jobId) => {
            if (!jobId) {
                return;
            }
            try {
                const endpoint = config.endpoints.detail.replace("{job_id}", encodeURIComponent(jobId));
                const response = await fetch(endpoint);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = await response.json();
                currentJobId = data.job_id;
                detailPlaceholder.classList.add("hidden");
                detailContainer.classList.remove("hidden");
                detailContainer.innerHTML = buildDetailHtml(data);
                await loadJobs();
            } catch (error) {
                console.error("[video_to_ppt] Failed to load job detail", error);
                detailContainer.innerHTML = `<p class="text-error">Failed to load job detail: ${escapeHtml(
                    error.message
                )}</p>`;
                detailContainer.classList.remove("hidden");
                detailPlaceholder.classList.add("hidden");
            }
        };

        const submitJob = async (event) => {
            event.preventDefault();
            console.info("[video_to_ppt] submit triggered");
            if (!form.checkValidity()) {
                form.reportValidity();
                return;
            }

            const formData = new FormData(form);
            const payload = {
                url: (formData.get("url") || "").trim(),
                similarity_threshold: parseFloat(formData.get("similarity_threshold")) || 0.95,
                min_interval_seconds: parseFloat(formData.get("min_interval_seconds")) || 2.0,
                skip_first_seconds: parseFloat(formData.get("skip_first_seconds")) || 0,
                fill_mode: formData.get("fill_mode") === "true",
                image_format: (formData.get("image_format") || "jpg").toLowerCase(),
                image_quality: parseInt(formData.get("image_quality"), 10) || 95,
            };

            const optionalFields = [
                ["title", formData.get("title")],
                ["subtitle", formData.get("subtitle")],
                ["job_id", formData.get("job_id")],
                ["file_pattern", formData.get("file_pattern")],
            ];

            optionalFields.forEach(([key, value]) => {
                if (!value) {
                    return;
                }
                const trimmed = value.trim();
                if (trimmed) {
                    payload[key] = trimmed;
                }
            });

            const extraArgsRaw = formData.get("extra_download_args");
            if (extraArgsRaw) {
                const extraArgs = extraArgsRaw
                    .split(/\r?\n|,/)
                    .map((item) => item.trim())
                    .filter(Boolean);
                if (extraArgs.length) {
                    payload.extra_download_args = extraArgs;
                }
            }

            statusLabel.textContent = "Submitting job...";
            statusLabel.classList.remove("text-error");

            try {
                console.info("[video_to_ppt] sending request", payload);
                const response = await fetch(config.endpoints.create, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    const message = await response.text();
                    throw new Error(message || `HTTP ${response.status}`);
                }
                const data = await response.json();
                form.reset();
                statusLabel.textContent = `Job accepted: ${data.job_id}`;
                currentJobId = data.job_id;
                console.info("[video_to_ppt] job accepted", data);
                await loadJobDetail(data.job_id);
            } catch (error) {
                console.error("[video_to_ppt] Failed to submit job", error);
                statusLabel.textContent = `Submission failed: ${error.message}`;
                statusLabel.classList.add("text-error");
            }
        };

        const handleTableClick = (event) => {
            const target = event.target;
            if (!target || !target.dataset.action) {
                return;
            }
            const jobId = target.dataset.jobId;
            if (!jobId) {
                return;
            }

            if (target.dataset.action === "view") {
                loadJobDetail(jobId);
            } else if (target.dataset.action === "reprocess") {
                reprocessJob(jobId);
            }
        };

        const processQueue = async () => {
            console.log("[video_to_ppt] processQueue clicked");
            if (!confirm("确定要批量处理所有待处理任务吗？")) {
                return;
            }
            
            processQueueBtn.disabled = true;
            processQueueBtn.textContent = "处理中...";
            
            try {
                console.log("[video_to_ppt] Calling endpoint:", config.endpoints.processQueue);
                const response = await fetch(config.endpoints.processQueue, {
                    method: "POST",
                });
                if (!response.ok) {
                    const message = await response.text();
                    throw new Error(message || `HTTP ${response.status}`);
                }
                const data = await response.json();
                console.log("[video_to_ppt] Process queue result:", data);
                alert(data.message || "队列处理已启动");
                await loadJobs();
            } catch (error) {
                console.error("[video_to_ppt] Failed to process queue", error);
                alert(`批量处理失败: ${error.message}`);
            } finally {
                processQueueBtn.disabled = false;
                processQueueBtn.textContent = "批量处理队列";
            }
        };

        const reprocessJob = async (jobId) => {
            if (!confirm(`确定要重新处理任务 ${jobId} 吗？`)) {
                return;
            }
            
            try {
                const endpoint = config.endpoints.reprocess.replace("{job_id}", encodeURIComponent(jobId));
                const response = await fetch(endpoint, {
                    method: "POST",
                });
                if (!response.ok) {
                    const message = await response.text();
                    throw new Error(message || `HTTP ${response.status}`);
                }
                const data = await response.json();
                alert("任务已重新加入队列");
                await loadJobDetail(jobId);
            } catch (error) {
                console.error("[video_to_ppt] Failed to reprocess job", error);
                alert(`重新处理失败: ${error.message}`);
            }
        };

        const stopAutoRefresh = () => {
            if (autoRefreshTimer) {
                clearInterval(autoRefreshTimer);
                autoRefreshTimer = null;
            }
        };

        const startAutoRefresh = () => {
            stopAutoRefresh();
            if (!autoRefreshToggle.checked) {
                return;
            }
            autoRefreshTimer = setInterval(loadJobs, REFRESH_INTERVAL);
        };

        refreshBtn.addEventListener("click", () => {
            loadJobs();
        });

        autoRefreshToggle.addEventListener("change", () => {
            if (autoRefreshToggle.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });

        console.info("[video_to_ppt] Adding event listeners");
        processQueueBtn.addEventListener("click", processQueue);
        // submitButton.addEventListener("click", submitJob);  // 不需要，form已经有submit事件
        form.addEventListener("submit", submitJob);
        jobsContainer.addEventListener("click", handleTableClick);
        console.info("[video_to_ppt] Event listeners added successfully");

        jobsContainer.innerHTML = `<p>${WAITING_MESSAGE}</p>`;
        loadJobs();
        startAutoRefresh();
    });
})();
