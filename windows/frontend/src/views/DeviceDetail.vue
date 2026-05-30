<template>
  <div class="device-detail">
    <div class="page-header">
      <h1>Device Detail</h1>
      <p class="subtitle">Select a device from Dashboard to view real-time waveforms</p>
    </div>
    <el-empty description="Phase 2 — IMU charts, parameter history & command console coming soon" />
  </div>
</template>

<style scoped>
.device-detail { animation: slideUp 0.4s ease; }
.page-header {
  padding: 20px 28px; margin: -32px -32px 24px;
  background: linear-gradient(135deg, #eef2ff 0%, #f0f4ff 100%);
  border-bottom: 1px solid var(--border);
}
.page-header h1 { font-size: 24px; font-weight: 700; }
.subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
</style>
