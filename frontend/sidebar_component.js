/**
 * sidebar_component.js
 * ─────────────────────────────────────────────────────────────────────────────
 * CyberComply – Shared Sidebar Vue 3 Component
 *
 * USAGE IN EVERY PAGE
 * ───────────────────
 * 1. Include this script AFTER Vue:
 *      <script src="sidebar_component.js"></script>
 *
 * 2. Drop the element anywhere inside your #app template:
 *      <cybercomply-sidebar
 *          :sidebar-open="sidebarOpen"
 *          @toggle="sidebarOpen = !sidebarOpen"
 *      ></cybercomply-sidebar>
 *
 * 3. Keep these two items in your page's own Vue data():
 *      sidebarOpen: false
 *
 * 4. Keep `.main-content` / `.shifted` on your page's main wrapper — the
 *    component emits @toggle so the parent controls the shift.
 *
 * TODO (when backend is ready):
 *   • Replace loadReports() fetch from localStorage with an API call:
 *       GET /api/reports?range=7   →  last7Days array
 *       GET /api/reports?range=30  →  last30Days array
 *   • Replace deleteReport() localStorage removal with:
 *       DELETE /api/reports/:id
 * ─────────────────────────────────────────────────────────────────────────────
 */

// ── Default mock data (seeded into localStorage on first run) ────────────────
const DEFAULT_REPORTS = {
  last7Days: [],
  last30Days: []
};

const STORAGE_KEY = 'cybercomply_reports';

// ── Component definition ─────────────────────────────────────────────────────
const CyberComplySidebar = {
  name: 'CyberComplySidebar',

  // The parent passes sidebarOpen so this component can react to it.
  // The component emits 'toggle' when the user clicks the hamburger.
  props: {
    sidebarOpen: {
      type: Boolean,
      default: false
    }
  },

  emits: ['toggle'],

  template: `
    <div>
      <!-- ── Sidebar panel ── -->
      <div class="sidebar" :class="{ open: sidebarOpen }">

        <!-- Icon bar: search + new analysis -->
        <div class="sidebar-icon-bar">
          <div class="sidebar-icon" @click="toggleSearch" title="Search documents">
            <svg viewBox="0 0 24 24">
              <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5
                       16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16
                       c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49
                       19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5
                       14 7.01 14 9.5 11.99 14 9.5 14z"/>
            </svg>
          </div>
          <div class="sidebar-icon" @click="goHome" title="Start new analysis">
            <svg viewBox="0 0 24 24">
              <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
            </svg>
          </div>
        </div>

        <!-- Search input -->
        <div class="search-container" :class="{ active: searchActive }">
          <input
            type="text"
            class="search-input"
            v-model="searchQuery"
            placeholder="Search documents..."
            @input="filterReports"
          >
        </div>

        <!-- Department filter (admin only) -->
        <div v-if="isAdmin && departments.length" class="sidebar-dept-filter">
          <select v-model="selectedDeptName" @change="onDeptChange" class="dept-select">
            <option :value="null">All Departments</option>
            <option v-for="dept in departments" :key="dept.dept_name" :value="dept.dept_name">
              {{ dept.dept_name }}
            </option>
          </select>
        </div>

        <!-- Last 7 Days -->
        <div class="sidebar-section">
          <div class="sidebar-header">
            <svg viewBox="0 0 24 24">
              <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10
                       C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20
                       c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58
                       8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/>
            </svg>
            LAST 7 DAYS
          </div>
          <div v-if="filteredLast7Days.length === 0" class="no-results">
            No results to display
          </div>
          <div v-else>
            <div
              v-for="report in filteredLast7Days"
              :key="report.report_id"
              class="sidebar-item"
            >
              <span class="sidebar-item-name" @click="openReport(report)">
                {{ report.display_name }}
              </span>
              <span
                class="sidebar-item-delete"
                @click.stop="confirmDelete(report, 'last7Days')"
                title="Delete report"
              >✕</span>
            </div>
          </div>
        </div>

        <!-- Last 30 Days -->
        <div class="sidebar-section">
          <div class="sidebar-header">
            <svg viewBox="0 0 24 24">
              <path d="M9 11H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2zm2-7h-1
                       V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89
                       2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V9h14v11z"/>
            </svg>
            LAST 30 DAYS
          </div>
          <div v-if="filteredLast30Days.length === 0" class="no-results">
            No results to display
          </div>
          <div v-else>
            <div
              v-for="report in filteredLast30Days"
              :key="report.report_id"
              class="sidebar-item"
            >
              <span class="sidebar-item-name" @click="openReport(report)">
                {{ report.display_name }}
              </span>
              <span
                class="sidebar-item-delete"
                @click.stop="confirmDelete(report, 'last30Days')"
                title="Delete report"
              >✕</span>
            </div>
          </div>
        </div>

      </div><!-- /sidebar -->

      <!-- ── Delete confirmation modal ── -->
      <div class="cc-modal-overlay" v-if="deleteModal.visible" @click.self="cancelDelete">
        <div class="cc-modal-box">
          <div class="cc-modal-icon">🗑️</div>
          <h3>Delete Report?</h3>
          <p>
            <strong>{{ deleteModal.report ? deleteModal.report.display_name : '' }}</strong>
            will be permanently removed. This action cannot be undone.
          </p>
          <div class="cc-modal-actions">
            <div class="cc-btn cc-btn-cancel" @click="cancelDelete">Cancel</div>
            <div class="cc-btn cc-btn-confirm" @click="executeDelete">Delete</div>
          </div>
        </div>
      </div>

    </div>
  `,

  data() {
    return {
      searchActive:       false,
      searchQuery:        '',
      last7Days:          [],
      last30Days:         [],
      filteredLast7Days:  [],
      filteredLast30Days: [],
      isAdmin:            false,
      departments:        [],   // [{ dept_id, dept_name }, ...] — populated for admins only
      selectedDeptName:   null,   // what the dropdown shows
      selectedDeptIds:    [],     // all dept_ids that share that name
      deleteModal: {
        visible: false,
        report:  null,
        bucket:  null   // 'last7Days' | 'last30Days'
      }
    };
  },

   mounted() {
    // Set isAdmin immediately from sessionStorage so the dropdown renders
    // without waiting for the loadDepartments() API response to complete.
    this.isAdmin = sessionStorage.getItem('userRole') === 'ADMINISTRATIVE_USER';

    this.loadDepartments();
    this.loadReports();

    // Re-fetch reports when user navigates back to this page via browser history.
    window.addEventListener('pageshow', (event) => {
        if (event.persisted) {
            this.isAdmin = sessionStorage.getItem('userRole') === 'ADMINISTRATIVE_USER';
            this.loadDepartments();
            this.loadReports();
        }
    });
  },

  methods: {
    // ── Data loading ──────────────────────────────────────────────────────────

    async loadDepartments() {
      const token = sessionStorage.getItem('authToken');
      if (!token) return;
      try {
        const res = await fetch('http://127.0.0.1:8000/ai/api/departments/', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) return;  // non-admins receive 403 — silently skip, isAdmin stays false
        const data = await res.json();
        this.isAdmin     = true;
        // departments is now [{ dept_name, dept_ids: [...] }]
        this.departments = data.departments || [];
      } catch (e) {
        console.warn('Sidebar: could not load departments:', e);
      }
    },

    async loadReports() {
      const token = sessionStorage.getItem('authToken');
      if (!token) return;
      try {
        const url = this.selectedDeptIds && this.selectedDeptIds.length
          ? `http://127.0.0.1:8000/ai/api/reports/?dept_ids=${encodeURIComponent(this.selectedDeptIds.join(','))}`
          : 'http://127.0.0.1:8000/ai/api/reports/';
        const res = await fetch(url, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        // Each item: { report_id, display_name, dept_id, generated_at, expires_at }
        this.last7Days  = data.last_7_days  || [];
        this.last30Days = data.last_30_days || [];
        this.filteredLast7Days  = [...this.last7Days];
        this.filteredLast30Days = [...this.last30Days];
      } catch (e) {
        console.warn('Sidebar: could not load reports:', e);
      }
    },

    async onDeptChange() {
      // Resolve the selected name to all matching dept_ids
      if (this.selectedDeptName) {
        const match = this.departments.find(d => d.dept_name === this.selectedDeptName);
        this.selectedDeptIds = match ? match.dept_ids : [];
      } else {
        this.selectedDeptIds = [];
      }
      await this.loadReports();
      this.filterReports();
    },

    // ── Public: called by the parent page after a new report is generated ────
    refreshReports() {
      this.loadReports();
    },

    // ── Navigation ────────────────────────────────────────────────────────────

    goHome() {
      window.location.href = 'home.html';
    },

    openReport(report) {
      // report is { report_id, display_name, view_token, ... }
      if (report.view_token) {
        window.location.href = `report_viewing.html?token=${encodeURIComponent(report.view_token)}`;
      } else {
        window.location.href = `report_viewing.html?report_id=${encodeURIComponent(report.report_id)}`;
      }
    },

    // ── Search / filter ───────────────────────────────────────────────────────

    toggleSearch() {
      this.searchActive = !this.searchActive;
      if (!this.searchActive) {
        this.searchQuery = '';
        this.filterReports();
      }
    },

    filterReports() {
      const q = this.searchQuery.toLowerCase();
      if (q === '') {
        this.filteredLast7Days  = [...this.last7Days];
        this.filteredLast30Days = [...this.last30Days];
      } else {
        this.filteredLast7Days  = this.last7Days.filter(r  => r.display_name.toLowerCase().includes(q));
        this.filteredLast30Days = this.last30Days.filter(r => r.display_name.toLowerCase().includes(q));
      }
    },

    // ── Delete flow ───────────────────────────────────────────────────────────

    confirmDelete(report, bucket) {
      this.deleteModal = { visible: true, report, bucket };
    },

    cancelDelete() {
      this.deleteModal = { visible: false, report: null, bucket: null };
    },

    async executeDelete() {
      const { report, bucket } = this.deleteModal;
      if (!report || !bucket) return;

      const token = sessionStorage.getItem('authToken');
      try {
        const res = await fetch(
          `http://127.0.0.1:8000/ai/api/reports/${report.report_id}/delete/`,
          {
            method:  'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          }
        );
        if (!res.ok) {
          console.error('Delete failed:', await res.text());
        }
      } catch (e) {
        console.error('Delete request failed:', e);
      }

      // Remove from in-memory list and re-filter regardless of server outcome
      // so the UI updates immediately
      this[bucket] = this[bucket].filter(r => r.report_id !== report.report_id);
      this.filterReports();
      this.cancelDelete();
    }
  }
};

// ── CSS injected once at runtime ─────────────────────────────────────────────
(function injectSidebarStyles() {
  if (document.getElementById('cybercomply-sidebar-styles')) return;

  const style = document.createElement('style');
  style.id = 'cybercomply-sidebar-styles';
  style.textContent = `
    /* ── Sidebar panel ── */
    .sidebar {
      position: fixed;
      left: 0;
      top: 56px;
      width: 280px;
      height: calc(100vh - 58px);
      background-color: #0d1420;
      transform: translateX(-100%);
      transition: transform 0.3s ease-in-out;
      z-index: 90;
      overflow-y: auto;
      padding: 20px 0;
      box-shadow: 4px 0 10px rgba(0,0,0,0.3);
    }
    .sidebar.open { transform: translateX(0); }

    .sidebar-icon-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 10px 15px 10px;
      margin-bottom: 20px;
      border-bottom: 2px solid #1a2845;
    }
    .sidebar-icon {
      width: 45px; height: 45px;
      background-color: #1a2845;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
    }
    .sidebar-icon:hover { background-color: #2a4a7c; transform: scale(1.05); }
    .sidebar-icon svg   { width: 22px; height: 22px; fill: #8b9dc3; transition: fill 0.3s; }
    .sidebar-icon:hover svg { fill: #ffffff; }

    .search-container       { padding: 0 20px 20px; display: none; }
    .search-container.active{ display: block; }
    .search-input {
      width: 100%;
      padding: 10px 15px;
      background-color: #1a2845;
      border: 2px solid #2a4a7c;
      border-radius: 8px;
      color: #ffffff;
      font-size: 14px;
      transition: border-color 0.3s;
    }
    .search-input:focus        { outline: none; border-color: #4a8fe7; }
    .search-input::placeholder { color: #6b7a99; }

    .sidebar-section  { margin-bottom: 30px; }
    .sidebar-header {
      padding: 10px 20px;
      font-size: 11px; font-weight: 600;
      color: #6b7a99; letter-spacing: 1.5px;
      display: flex; align-items: center; gap: 10px;
    }
    .sidebar-header svg { width: 14px; height: 14px; fill: #6b7a99; }

    /* ── Report row (name + delete button) ── */
    .sidebar-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px 10px 20px;
      color: #c5d0e6;
      border-left: 3px solid transparent;
      transition: all 0.2s;
    }
    .sidebar-item:hover {
      background-color: #1a2845;
      border-left-color: #4a8fe7;
      color: #ffffff;
    }
    .sidebar-item-name {
      flex: 1;
      cursor: pointer;
      font-size: 14px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      padding-right: 8px;
    }
    .sidebar-item-delete {
      flex-shrink: 0;
      width: 22px; height: 22px;
      display: flex; align-items: center; justify-content: center;
      border-radius: 50%;
      font-size: 11px;
      color: #6b7a99;
      cursor: pointer;
      transition: background-color 0.2s, color 0.2s;
      opacity: 0;
    }
    .sidebar-item:hover .sidebar-item-delete { opacity: 1; }
    .sidebar-item-delete:hover {
      background-color: #c0392b;
      color: #ffffff;
    }

    .no-results {
      padding: 12px 20px;
      color: #6b7a99; font-size: 12px; font-style: italic;
    }

    /* ── Delete confirmation modal ── */
    .cc-modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.6);
      display: flex; align-items: center; justify-content: center;
      z-index: 500;
      animation: ccFadeIn 0.2s ease;
    }
    @keyframes ccFadeIn { from { opacity: 0; } to { opacity: 1; } }

    .cc-modal-box {
      background: #1a2845;
      border: 1px solid #2a4a7c;
      border-radius: 16px;
      padding: 36px 32px;
      width: 340px;
      text-align: center;
      box-shadow: 0 12px 40px rgba(0,0,0,0.5);
      animation: ccPopIn 0.2s ease;
    }
    @keyframes ccPopIn {
      from { transform: scale(0.92); opacity: 0; }
      to   { transform: scale(1);    opacity: 1; }
    }

    .cc-modal-icon {
      font-size: 38px;
      margin-bottom: 14px;
    }
    .cc-modal-box h3 {
      font-size: 17px; font-weight: 700;
      color: #ffffff; letter-spacing: 0.5px;
      margin-bottom: 10px;
    }
    .cc-modal-box p {
      font-size: 13px; color: #8b9dc3;
      line-height: 1.7; margin-bottom: 24px;
    }
    .cc-modal-box p strong { color: #c5d0e6; }

    .cc-modal-actions {
      display: flex; gap: 12px; justify-content: center;
    }
    .cc-btn {
      padding: 9px 26px;
      border-radius: 20px;
      font-size: 13px; font-weight: 600; letter-spacing: 0.5px;
      cursor: pointer;
      transition: background 0.2s, transform 0.2s;
    }
    .cc-btn-cancel {
      background: #2a3f5f; color: #c5d0e6;
      border: 1px solid #3a5a8a;
    }
    .cc-btn-cancel:hover { background: #3a5a8a; transform: translateY(-1px); }
    .cc-btn-confirm {
      background: #c0392b; color: #ffffff;
    }
    .cc-btn-confirm:hover { background: #e74c3c; transform: translateY(-1px); }

    /* ── Sidebar scrollbar ── */
    .sidebar::-webkit-scrollbar       { width: 6px; }
    .sidebar::-webkit-scrollbar-track { background: #0d1420; }
    .sidebar::-webkit-scrollbar-thumb { background: #2a4a7c; border-radius: 3px; }
    .sidebar::-webkit-scrollbar-thumb:hover { background: #4a8fe7; }

    /* ── Department filter dropdown (admin only) ── */
    .sidebar-dept-filter {
      padding: 0 20px 16px;
    }
    .dept-select {
      width: 100%;
      padding: 8px 12px;
      background-color: #1a2845;
      border: 2px solid #2a4a7c;
      border-radius: 8px;
      color: #c5d0e6;
      font-size: 13px;
      cursor: pointer;
      transition: border-color 0.3s;
      appearance: none;
    }
    .dept-select:focus  { outline: none; border-color: #4a8fe7; }
    .dept-select option { background-color: #1a2845; color: #c5d0e6; }

    /* ── Responsive: sidebar overlays on small screens ── */
    @media screen and (max-width: 1200px) {
      .sidebar { position: fixed; box-shadow: 4px 0 20px rgba(0,0,0,0.5); }
      .main-content.shifted { margin-left: 0; }
    }
  `;
  document.head.appendChild(style);
})();

// ── Registration helper (called in each page's script block) ─────────────────
/**
 * registerSidebarComponent(app)
 * Call this before app.mount('#app') in every page.
 *
 * Example:
 *   const app = createApp({ ... });
 *   registerSidebarComponent(app);
 *   app.mount('#app');
 */
function registerSidebarComponent(app) {
  app.component('cybercomply-sidebar', CyberComplySidebar);
}