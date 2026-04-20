document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('.nav-links li');
    const views = document.querySelectorAll('.view');
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            const targetId = `view-${link.dataset.tab}`;
            if (!document.getElementById(targetId)) return;
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            views.forEach(v => v.classList.remove('active-view'));
            document.getElementById(targetId).classList.add('active-view');
            if(link.dataset.tab === 'tasks') fetchTasks();
        });
    });

    const dateDisplay = document.getElementById('current-date-display');
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateDisplay.textContent = new Date().toLocaleDateString('pt-BR', options);

    let efficiencyChart = null;
    function initChart() {
        const ctx = document.getElementById('efficiencyChart').getContext('2d');
        efficiencyChart = new Chart(ctx, {
            type: 'doughnut',
            data: { labels: ['Aproveitado', 'Ocioso'], datasets: [{ data: [0, 100], backgroundColor: ['#10b981', 'rgba(255,255,255,0.05)'], borderWidth: 0, cutout: '80%' }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { enabled: false } }, animation: { animateScale: true } }
        });
    }
    initChart();

    async function fetchStatus() {
        try {
            const res = await fetch('api/status');
            const data = await res.json();
            updateStatusUI(data);
            updateSystemDot(true);
            // Update tracker indicator
            const trackerDot = document.getElementById('tracker-status-dot');
            const trackerText = document.getElementById('tracker-status-text');
            if (data.tracker_connected) {
                trackerDot.className = 'status-dot online';
                trackerText.textContent = 'Tracker conectado';
            } else {
                trackerDot.className = 'status-dot offline';
                trackerText.textContent = 'Tracker offline';
            }
        } catch (e) { console.error(e); updateSystemDot(false); }
    }

    async function fetchReport() {
        try {
            const res = await fetch('api/report/today');
            const data = await res.json();
            updateReportUI(data);
        } catch (e) { console.error(e); }
    }

    function updateSystemDot(isOnline) {
        const dot = document.getElementById('system-status-dot');
        const text = document.getElementById('system-status-text');
        if (isOnline) { dot.className = 'status-dot online'; text.textContent = 'Backend Conectado'; }
        else { dot.className = 'status-dot offline'; text.textContent = 'Backend Offline'; }
    }

    function updateStatusUI(status) {
        const titleEl = document.getElementById('state-title');
        const subEl = document.getElementById('state-subtitle');
        const iconEl = document.getElementById('state-icon');
        iconEl.className = 'state-icon';
        if (status.is_studying) {
            titleEl.textContent = 'Estudando Focado';
            const dur = formatTime(status.current_study_duration_minutes || 0);
            subEl.textContent = `Sessão ativa há ${dur}`;
            iconEl.classList.add('state-study', 'pulse'); iconEl.innerHTML = '<i class="ph-fill ph-brain"></i>';
        } else if (status.is_useful_time) {
            titleEl.textContent = 'Tempo Útil (Ocioso)';
            subEl.textContent = `Você deveria estar estudando.`;
            iconEl.classList.add('state-useful'); iconEl.innerHTML = '<i class="ph-fill ph-warning-circle"></i>';
        } else if (status.is_home) {
            titleEl.textContent = 'Em Casa (Livre)';
            subEl.textContent = 'Descanse, você está fora do horário útil.';
            iconEl.innerHTML = '<i class="ph-fill ph-house"></i>';
        } else {
            titleEl.textContent = 'Fora de Casa';
            subEl.textContent = `Status HA: ${status.presence}`;
            iconEl.innerHTML = '<i class="ph-fill ph-car-profile"></i>';
        }
    }

    function formatTime(totalMinutes) {
        const totalSecs = Math.round(totalMinutes * 60);
        const h = Math.floor(totalSecs / 3600);
        const m = Math.floor((totalSecs % 3600) / 60);
        const s = totalSecs % 60;
        if (h > 0) return `${h}h ${m}m ${s}s`;
        if (m > 0) return `${m}m ${s}s`;
        return `${s}s`;
    }

    function updateReportUI(report) {
        document.getElementById('metric-study').textContent = formatTime(report.total_study_minutes);
        document.getElementById('metric-useful').textContent = formatTime(report.total_useful_minutes);
        document.getElementById('metric-streak').textContent = `${report.streak_days} dias`;
        const eff = Math.round(report.study_efficiency_pct);
        document.getElementById('efficiency-value').textContent = `${eff}%`;
        let color = '#10b981'; if (eff < 40) color = '#ef4444'; else if (eff < 70) color = '#f59e0b';
        efficiencyChart.data.datasets[0].data = [eff, Math.max(0, 100 - eff)];
        efficiencyChart.data.datasets[0].backgroundColor[0] = color;
        efficiencyChart.update();
        const renderList = (id, data, formatter) => {
            const ul = document.getElementById(id); ul.innerHTML = '';
            if (!data || data.length === 0) { ul.innerHTML = '<li>Nenhum dado registrado</li>'; return; }
            data.forEach(item => { const li = document.createElement('li'); li.innerHTML = `<span>${item.name}</span> <span class="text-muted">${formatter(item)}</span>`; ul.appendChild(li); });
        };
        renderList('top-apps-list', report.top_apps, i => formatTime(i.minutes));
        renderList('top-keywords-list', report.top_keywords, i => formatTime(i.minutes));
    }

    async function fetchTasks() {
        const list = document.getElementById('google-tasks-list');
        list.innerHTML = '<div class="empty-state">Carregando tarefas do Google...</div>';
        try {
            const res = await fetch('api/tasks'); const data = await res.json();
            if (data.status === 'not_initialized') {
                list.innerHTML = `<div class="empty-state text-amber"><i class="ph ph-warning" style="font-size:2rem; margin-bottom:1rem;"></i><br>Google Tasks não inicializado.</div>`;
                return;
            }
            document.getElementById('task-pending-count').textContent = data.pending || 0;
            document.getElementById('task-completed-count').textContent = data.completed || 0;
            list.innerHTML = '';
            if (data.pending_tasks) data.pending_tasks.forEach(t => list.appendChild(createTaskEl(t, false)));
            if (data.completed_tasks) data.completed_tasks.forEach(t => list.appendChild(createTaskEl(t, true)));
            if (list.innerHTML === '') list.innerHTML = '<div class="empty-state">Nenhuma tarefa encontrada.</div>';
        } catch (e) { list.innerHTML = '<div class="empty-state text-rose">Erro ao carregar tarefas.</div>'; }
    }

    function createTaskEl(task, isCompleted) {
        const div = document.createElement('div'); div.className = `task-item ${isCompleted ? 'completed' : ''}`;
        const dueText = task.due ? `<p style="margin-top:0.5rem; color:var(--accent); font-size:0.85rem;">Due: ${new Date(task.due).toLocaleDateString()}</p>` : '';
        div.innerHTML = `<div class="task-checkbox" data-id="${task.id}"></div><div><div class="task-title">${task.title}</div>${task.notes ? `<div class="task-notes">${task.notes}</div>` : ''}${dueText}</div>`;
        if (!isCompleted) {
            const cb = div.querySelector('.task-checkbox');
            cb.addEventListener('click', async () => {
                cb.innerHTML = '...';
                try { await fetch(`api/tasks/${task.id}/complete`, {method: 'POST'}); fetchTasks(); } 
                catch(e) { cb.innerHTML = ''; console.error(e); }
            });
        }
        return div;
    }
    document.getElementById('btn-sync-tasks').addEventListener('click', fetchTasks);

    let pomoInterval; let timeLeft = 25 * 60; let isRunning = false;
    const timeDisplay = document.getElementById('pomo-time');
    const startBtn = document.getElementById('btn-pomo-start');
    function updateTimerDisplay() { const m = Math.floor(timeLeft / 60).toString().padStart(2, '0'); const s = (timeLeft % 60).toString().padStart(2, '0'); timeDisplay.textContent = `${m}:${s}`; }
    startBtn.addEventListener('click', () => {
        if (isRunning) { clearInterval(pomoInterval); isRunning = false; startBtn.innerHTML = '<i class="ph ph-play"></i>'; } 
        else {
            isRunning = true; startBtn.innerHTML = '<i class="ph ph-pause"></i>';
            pomoInterval = setInterval(() => {
                if (timeLeft > 0) { timeLeft--; updateTimerDisplay(); } 
                else { clearInterval(pomoInterval); isRunning = false; alert("Pomodoro finalizado!"); startBtn.innerHTML = '<i class="ph ph-play"></i>'; }
            }, 1000);
        }
    });
    document.getElementById('btn-pomo-reset').addEventListener('click', () => {
        clearInterval(pomoInterval); isRunning = false; timeLeft = 25 * 60; updateTimerDisplay(); startBtn.innerHTML = '<i class="ph ph-play"></i>';
    });

    setInterval(fetchStatus, 10000); setInterval(fetchReport, 30000);
    fetchStatus(); fetchReport();
});
