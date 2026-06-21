const state = {
  locale: {},
  workflowName: "web_workflow.json",
  lastWorkflow: null,
  lastScan: null,
  selectedPaths: {
    main: "",
    DEM: "",
    mainRole: "",
  },
  selectedQuestion: "",
  lastAnalysis: null,
};

const $ = (id) => document.getElementById(id);

function t(key, fallback = key) {
  return state.locale[key] || fallback;
}

async function loadLocale() {
  const response = await fetch("/locales/zh-CN.json", { cache: "no-store" });
  state.locale = await response.json();
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.getAttribute("data-i18n-placeholder")));
  });
}

function setStatus(messageKeyOrText, level = "info", raw = false) {
  const node = $("statusLine");
  node.textContent = raw ? messageKeyOrText : t(messageKeyOrText, messageKeyOrText);
  node.className = `status-line ${level}`;
}

function log(payload) {
  $("logBox").textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

function setBusy(isBusy, messageKey) {
  document.body.classList.toggle("busy", isBusy);
  if (messageKey) setStatus(messageKey, isBusy ? "running" : "info");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

function roleLabel(role) {
  return t(`role.${role}`, role);
}

function processLabel(status) {
  return t(`process.${status}`, status);
}

function moduleStatusLabel(status) {
  return t(`module.${status}`, status);
}

function joinPath(root, name) {
  const cleanRoot = root.trim().replace(/[\\\/]+$/, "");
  const cleanName = (name.trim() || "web_run").replace(/[\\\/:*?"<>|]/g, "_");
  return cleanRoot ? `${cleanRoot}\\${cleanName}` : cleanName;
}

function syncOutputDir() {
  $("outputDir").value = joinPath($("resultRoot").value, $("runName").value);
}

function workflowNeedsToken(workflow, token) {
  return workflowExecutableText(workflow).includes(token);
}

function workflowExecutableText(workflow) {
  const executableSteps = (workflow?.steps || []).filter((step) => step.engine !== "pending");
  return JSON.stringify({ ...workflow, steps: executableSteps });
}

function workflowParameterTokens(workflow) {
  const text = workflowExecutableText(workflow);
  const tokens = new Set();
  for (const match of text.matchAll(/<([A-Za-z0-9_]+)>/g)) {
    tokens.add(match[1]);
  }
  if (/\bthreshold\b/.test(text)) tokens.add("threshold");
  tokens.delete("DEM");
  return [...tokens].sort();
}

const LAYER_FIELD_TOKENS = new Set([
  "DEM",
  "OBSERVER_POINTS",
  "TARGET_LAYER",
  "JOIN_TABLE",
  "ZONE_LAYER",
  "VALUE_RASTER",
  "TEMPLATE_LAYER",
  "SPLIT_LAYER",
  "OVERLAY_LAYER",
  "BUILDING_LAYER",
  "CANDIDATE_POINTS",
  "BUILDING_3D",
]);

const FIELD_TOKENS = new Set([
  "TARGET_FIELD",
  "JOIN_FIELD",
  "ZONE_FIELD",
  "FIELDS_TO_COPY",
  "STATS",
  "HEIGHT_FIELD",
]);

function parameterLabel(key) {
  const labels = {
    threshold: "汇流累积阈值 threshold",
    distance: "缓冲距离 distance",
    DEM: "DEM / 高程栅格",
    OBSERVER_POINTS: "观察点图层 OBSERVER_POINTS",
    OBSERVER_XY: "单个观察点坐标 OBSERVER_XY",
    observer_height: "观察高度 observer_height",
    MAX_DISTANCE: "最大可视距离 MAX_DISTANCE",
    TARGET_LAYER: "目标图层 TARGET_LAYER",
    JOIN_TABLE: "连接表 JOIN_TABLE",
    TARGET_FIELD: "目标图层连接字段 TARGET_FIELD",
    JOIN_FIELD: "连接表字段 JOIN_FIELD",
    ZONE_LAYER: "分区面图层 ZONE_LAYER",
    ZONE_FIELD: "分区编号字段 ZONE_FIELD",
    VALUE_RASTER: "统计栅格 VALUE_RASTER",
    STATS: "统计项 STATS",
    FIELDS_TO_COPY: "复制字段 FIELDS_TO_COPY",
    TEMPLATE_LAYER: "模板/目标图层 TEMPLATE_LAYER",
    SPLIT_LAYER: "切割线图层 SPLIT_LAYER",
    OVERLAY_LAYER: "覆盖/裁剪边界图层 OVERLAY_LAYER",
    BUILDING_LAYER: "建筑图层 BUILDING_LAYER",
    CANDIDATE_POINTS: "候选点/质心点 CANDIDATE_POINTS",
    BUILDING_3D: "三维建筑图层 BUILDING_3D",
    HEIGHT_FIELD: "建筑高度字段 HEIGHT_FIELD",
    CELL_SIZE: "输出像元大小 CELL_SIZE",
    SUN_AZIMUTH: "太阳方位角 SUN_AZIMUTH",
    SUN_ALTITUDE: "太阳高度角 SUN_ALTITUDE",
    SUN_DATETIME: "日照分析时间 SUN_DATETIME",
    GEOMETRY_TYPE: "要素类型 GEOMETRY_TYPE",
    DELTA_X: "X 方向移动量 DELTA_X",
    DELTA_Y: "Y 方向移动量 DELTA_Y",
    ANGLE: "旋转角度 ANGLE",
    ANCHOR: "旋转中心 ANCHOR",
    MAX_NODES: "最大节点数 MAX_NODES",
  };
  return labels[key] || key;
}

function parameterPlaceholder(key) {
  const placeholders = {
    MAIN: "默认使用左侧主数据路径",
    DEM: "选择或输入 DEM / 高程栅格路径",
    threshold: "例如：500",
    distance: "例如：500，单位通常为米",
    OBSERVER_POINTS: "选择或输入观察点图层路径",
    OBSERVER_XY: "例如：37521165,3318598",
    observer_height: "例如：10",
    MAX_DISTANCE: "例如：5000，单位通常为米；不限制时可先填 0",
    TARGET_LAYER: "选择需要追加字段的矢量图层",
    JOIN_TABLE: "选择 CSV/XLSX/DBF 等属性表",
    TARGET_FIELD: "例如：XZQDM、NAME、id",
    JOIN_FIELD: "例如：XZQDM、NAME、id",
    ZONE_LAYER: "选择用于分区统计的面图层",
    ZONE_FIELD: "例如：id、NAME、XZQDM",
    VALUE_RASTER: "选择被统计的栅格数据",
    STATS: "QGIS 统计代码，例如 2 表示均值",
    FIELDS_TO_COPY: "例如：POP,GDP；不确定时填 * 作为占位",
    TEMPLATE_LAYER: "选择要参考字段结构的图层；也可手动填写输出目标",
    SPLIT_LAYER: "选择用于切割的线图层",
    OVERLAY_LAYER: "选择研究区边界、掩膜或裁剪范围",
    BUILDING_LAYER: "选择建筑面/建筑轮廓转换后的面图层",
    CANDIDATE_POINTS: "选择候选建筑质心点或候选设施点",
    BUILDING_3D: "选择具有高度/Z值的三维建筑图层",
    HEIGHT_FIELD: "例如：height、楼层数计算后的高度字段",
    CELL_SIZE: "例如：1 或 5，单位按当前投影坐标",
    SUN_AZIMUTH: "冬至日12时常用 180",
    SUN_ALTITUDE: "冬至日12时示例 44.3",
    SUN_DATETIME: "例如：2026-12-22 12:00",
    GEOMETRY_TYPE: "point / line / polygon",
    DELTA_X: "例如：10，单位按当前投影坐标",
    DELTA_Y: "例如：0，单位按当前投影坐标",
    ANGLE: "例如：30，单位为度",
    ANCHOR: "例如：0,0；不确定时先填 0,0",
    MAX_NODES: "例如：256",
  };
  return placeholders[key] || "填写参数值或数据路径";
}

function workflowText(workflow = state.lastWorkflow) {
  return JSON.stringify(workflow || {});
}

function workflowHasAny(workflow, words) {
  const text = workflowText(workflow).toLowerCase();
  return words.some((word) => text.includes(word.toLowerCase()));
}

function scanItems(roles) {
  const groups = state.lastScan?.groups || {};
  return roles.flatMap((role) => groups[role] || []);
}

function firstScanPath(roles) {
  return scanItems(roles)[0]?.path || "";
}

function optionHtml(items, selected = "") {
  const normalized = selected || "";
  const rows = [`<option value="">手动填写或从下拉选择</option>`];
  for (const item of items) {
    const value = item.path || "";
    const label = `${roleLabel(item.role)} | ${item.name || value}`;
    rows.push(`<option value="${value}" ${value === normalized ? "selected" : ""}>${label}</option>`);
  }
  return rows.join("");
}

function inferParameterValue(key) {
  const task = $("taskText").value || "";
  const compact = task.replace(/\s+/g, " ");
  if (key === "threshold") {
    const patterns = [
      /阈值[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)/i,
      /threshold[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)/i,
      /汇流[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)/i,
      /[>＞]\s*([0-9]+(?:\.[0-9]+)?)/,
    ];
    for (const pattern of patterns) {
      const match = compact.match(pattern);
      if (match) return match[1];
    }
  }
  if (key === "distance") {
    const patterns = [
      /缓冲[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(m|米|km|千米)/i,
      /([0-9]+(?:\.[0-9]+)?)\s*(m|米)\s*(范围|缓冲|内|以内|区域)/i,
      /([0-9]+(?:\.[0-9]+)?)\s*(km|千米)\s*(范围|缓冲|内|以内|区域)/i,
    ];
    for (const pattern of patterns) {
      const match = compact.match(pattern);
      if (!match) continue;
      const value = Number(match[1]);
      const unit = match[2] || "";
      if (Number.isFinite(value)) return String(/km|千米/i.test(unit) ? value * 1000 : value);
    }
    if (/(缓冲|周边|范围|以内|服务区|buffer|distance)/i.test(compact)) return "500";
  }
  if (key === "observer_height" || key === "OBSERVER_HEIGHT") {
    const match = compact.match(/(观察|瞭望|塔|高度)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(m|米)?/i);
    if (match) return match[2];
  }
  if (key === "OBSERVER_XY") {
    const match = compact.match(/([0-9]{5,}(?:\.[0-9]+)?)\s*[,，]\s*([0-9]{5,}(?:\.[0-9]+)?)/);
    if (match) return `${match[1]},${match[2]}`;
  }
  if (key === "MAX_DISTANCE") {
    const patterns = [
      /(半径|可视距离|分析距离|最大距离|范围)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(km|千米|m|米)?/i,
      /([0-9]+(?:\.[0-9]+)?)\s*(km|千米|m|米)\s*(半径|可视距离|分析距离|最大距离|范围)/i,
    ];
    for (const pattern of patterns) {
      const match = compact.match(pattern);
      if (!match) continue;
      const rawValue = match[2] && /[0-9]/.test(match[2]) ? match[2] : match[1];
      const value = Number(rawValue);
      const unit = match[3] || match[2] || "";
      if (Number.isFinite(value)) return String(/km|千米/i.test(unit) ? value * 1000 : value);
    }
    if (/(可视域|视域|viewshed|瞭望|观察点)/i.test(compact)) return "5000";
  }
  if (key === "ANGLE") {
    const match = compact.match(/(?:旋转|角度|rotate)[^0-9-]{0,12}(-?[0-9]+(?:\.[0-9]+)?)/i);
    if (match) return match[1];
  }
  if (key === "DELTA_X") {
    const match = compact.match(/(?:x|X|横向|东西|平移|移动)[^0-9-]{0,12}(-?[0-9]+(?:\.[0-9]+)?)/i);
    if (match) return match[1];
  }
  if (key === "DELTA_Y") {
    const match = compact.match(/(?:y|Y|纵向|南北)[^0-9-]{0,12}(-?[0-9]+(?:\.[0-9]+)?)/i);
    if (match) return match[1];
  }
  if (key === "MAX_NODES") return "256";
  if (key === "ANCHOR") return "0,0";
  if (key === "GEOMETRY_TYPE") {
    if (/点|point/i.test(compact)) return "point";
    if (/线|line/i.test(compact)) return "line";
    if (/面|polygon|区/i.test(compact)) return "polygon";
  }
  if (key === "HEIGHT_FIELD") {
    if (/楼层|层数/.test(compact)) return "楼层数";
    if (/高度|height/i.test(compact)) return "height";
  }
  if (key === "CELL_SIZE") return "1";
  if (key === "SUN_AZIMUTH") return "180";
  if (key === "SUN_ALTITUDE") return "44.3";
  if (key === "SUN_DATETIME") return "2026-12-22 12:00";
  return "";
}

function hasExplicitDistance() {
  const task = $("taskText").value || "";
  const compact = task.replace(/\s+/g, " ");
  return [
    /缓冲[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(m|米|km|千米)/i,
    /([0-9]+(?:\.[0-9]+)?)\s*(m|米)\s*(范围|缓冲|周边|内|以内|区域)/i,
    /([0-9]+(?:\.[0-9]+)?)\s*(km|千米)\s*(范围|缓冲|周边|内|以内|区域)/i,
  ].some((pattern) => pattern.test(compact));
}

function isGuessedParameter(key, value) {
  return key === "distance" && value === "500" && !hasExplicitDistance();
}

function renderRepairFeedback(items) {
  const box = $("repairFeedback");
  if (!box) return;
  if (!items.length) {
    box.className = "repair-feedback warning";
    box.innerHTML = `
      <strong>未找到可自动修复的参数</strong>
      <span>请检查题目中是否写明阈值、缓冲距离或观察高度；没有写明时需要手动填写。</span>
    `;
    return;
  }
  const filled = items.filter((item) => item.value);
  const missing = items.filter((item) => !item.value);
  box.className = `repair-feedback ${missing.length ? "warning" : "ok"}`;
  box.innerHTML = `
    <strong>${filled.length ? `已自动填入 ${filled.length} 项` : "没有自动填入参数"}</strong>
    ${filled.map((item) => `<span>${item.label} = ${item.value}${item.guessed ? "（默认建议，执行前确认）" : ""}</span>`).join("")}
    ${missing.length ? `<strong>仍需手动确认</strong>${missing.map((item) => `<span>${item.label}</span>`).join("")}` : ""}
    <em>下一步：点击“预览命令”。</em>
  `;
}

function statusPriority(status) {
  const order = {
    failed: 0,
    blocked: 1,
    pending: 2,
    needs_mapping: 2,
    needs_confirmation: 3,
    dry_run: 4,
    ready: 4,
    completed: 5,
    skipped: 6,
  };
  return order[status] ?? 9;
}

function unresolvedTokensFromRows(rows = []) {
  const tokens = new Set();
  for (const row of rows) {
    const text = `${row.message || ""} ${(row.command || []).join(" ")}`;
    for (const match of text.matchAll(/<([A-Za-z0-9_]+)>/g)) tokens.add(match[1]);
    if (/\bdistance\b/.test(text)) tokens.add("distance");
    if (/\bthreshold\b/.test(text)) tokens.add("threshold");
  }
  return [...tokens].sort();
}

function highlightMissingMappings(rows = []) {
  document.querySelectorAll(".mapping-row.missing").forEach((node) => node.classList.remove("missing"));
  const tokens = unresolvedTokensFromRows(rows);
  for (const token of tokens) {
    document.querySelectorAll(`[data-var-key="${token}"]`).forEach((input) => {
      input.closest(".mapping-row")?.classList.add("missing");
    });
  }
  return tokens;
}

function renderVariableMappings(workflow = state.lastWorkflow) {
  const box = $("variableMappings");
  const existingValues = {};
  box.querySelectorAll("[data-var-key]").forEach((input) => {
    const key = input.getAttribute("data-var-key");
    if (key && input.value.trim()) existingValues[key] = input.value.trim();
  });
  box.innerHTML = "";
  const mappings = [
    {
      key: "MAIN",
      label: t("label.mainData"),
      value: existingValues.MAIN || state.selectedPaths.main || $("dataPath").value.trim(),
      required: true,
    },
  ];
  for (const token of workflowParameterTokens(workflow)) {
    if (LAYER_FIELD_TOKENS.has(token) || FIELD_TOKENS.has(token)) continue;
    const value = existingValues[token] || inferParameterValue(token);
    mappings.push({ key: token, label: parameterLabel(token), value, required: true, guessed: isGuessedParameter(token, value) });
  }
  for (const mapping of mappings) {
    const wrap = document.createElement("label");
    wrap.className = `mapping-row ${mapping.guessed ? "guessed" : ""}`;
    wrap.innerHTML = `
      <span>${mapping.label}${mapping.required ? " *" : ""}</span>
      <input data-var-key="${mapping.key}" value="${mapping.value || ""}" placeholder="${parameterPlaceholder(mapping.key)}" />
      ${mapping.guessed ? `<small>系统未在题目中找到明确距离，已先填 500 米；真实执行前请确认。</small>` : ""}
    `;
    box.appendChild(wrap);
  }
  renderLayerFieldMappings(workflow);
}

function layerFieldRows(workflow = state.lastWorkflow) {
  const tokens = new Set(workflowParameterTokens(workflow));
  const rows = [];
  const vectorItems = scanItems(["boundary", "vector", "hydro_vector"]);
  const tableItems = scanItems(["table"]);
  const rasterItems = scanItems(["dem", "raster", "remote_sensing"]);
  const needsJoin = tokens.has("JOIN_TABLE") || workflowHasAny(workflow, ["join", "连接", "字段", "属性表", "csv", "xlsx", "GDP"]);
  const needsZonal = tokens.has("ZONE_LAYER") || workflowHasAny(workflow, ["zonal", "分区统计", "区域统计", "统计"]);
  const needsObserver = tokens.has("OBSERVER_POINTS");
  const needsDem = workflowNeedsToken(workflow, "<DEM>");
  const needsTemplate = tokens.has("TEMPLATE_LAYER");
  const needsTarget = tokens.has("TARGET_LAYER");
  const needsSplit = tokens.has("SPLIT_LAYER");
  const needsOverlay = tokens.has("OVERLAY_LAYER");
  const needsBuilding = tokens.has("BUILDING_LAYER") || tokens.has("BUILDING_3D");
  const needsCandidatePoints = tokens.has("CANDIDATE_POINTS");

  if (needsDem && !["dem", "raster", "remote_sensing"].includes(state.selectedPaths.mainRole)) {
    rows.push({ key: "DEM", type: "layer", options: rasterItems, value: state.selectedPaths.DEM || firstScanPath(["dem", "raster", "remote_sensing"]) });
  }
  if (needsTemplate) {
    rows.push({ key: "TEMPLATE_LAYER", type: "layer", options: vectorItems, value: firstScanPath(["vector", "boundary"]) });
  }
  if (needsTarget && !needsJoin) {
    rows.push({ key: "TARGET_LAYER", type: "layer", options: vectorItems, value: state.selectedPaths.mainRole === "vector" || state.selectedPaths.mainRole === "boundary" ? state.selectedPaths.main : firstScanPath(["boundary", "vector"]) });
  }
  if (needsSplit) {
    rows.push({ key: "SPLIT_LAYER", type: "layer", options: vectorItems, value: firstScanPath(["vector", "hydro_vector", "boundary"]) });
  }
  if (needsOverlay) {
    rows.push({ key: "OVERLAY_LAYER", type: "layer", options: vectorItems, value: firstScanPath(["boundary", "vector"]) });
  }
  if (needsBuilding) {
    rows.push({ key: "BUILDING_LAYER", type: "layer", options: vectorItems, value: firstScanPath(["vector", "boundary"]) });
  }
  if (tokens.has("HEIGHT_FIELD")) {
    rows.push({ key: "HEIGHT_FIELD", type: "field", value: inferParameterValue("HEIGHT_FIELD") });
  }
  if (tokens.has("BUILDING_3D")) {
    rows.push({ key: "BUILDING_3D", type: "layer", options: vectorItems, value: firstScanPath(["vector", "boundary"]) });
  }
  if (needsCandidatePoints) {
    rows.push({ key: "CANDIDATE_POINTS", type: "layer", options: vectorItems, value: firstScanPath(["vector"]) });
  }
  if (needsObserver) {
    rows.push({ key: "OBSERVER_POINTS", type: "layer", options: vectorItems, value: firstScanPath(["vector", "boundary"]) });
  }
  if (needsJoin) {
    rows.push({ key: "TARGET_LAYER", type: "layer", options: vectorItems, value: state.selectedPaths.mainRole === "vector" || state.selectedPaths.mainRole === "boundary" ? state.selectedPaths.main : firstScanPath(["boundary", "vector"]) });
    rows.push({ key: "JOIN_TABLE", type: "layer", options: tableItems, value: firstScanPath(["table"]) });
    rows.push({ key: "TARGET_FIELD", type: "field", value: inferFieldName("target") });
    rows.push({ key: "JOIN_FIELD", type: "field", value: inferFieldName("join") });
    rows.push({ key: "FIELDS_TO_COPY", type: "field", value: "*" });
  }
  if (needsZonal) {
    rows.push({ key: "ZONE_LAYER", type: "layer", options: vectorItems, value: firstScanPath(["boundary", "vector"]) });
    rows.push({ key: "ZONE_FIELD", type: "field", value: inferFieldName("zone") });
    rows.push({ key: "VALUE_RASTER", type: "layer", options: rasterItems, value: state.selectedPaths.mainRole === "raster" || state.selectedPaths.mainRole === "dem" ? state.selectedPaths.main : firstScanPath(["raster", "dem", "remote_sensing"]) });
    rows.push({ key: "STATS", type: "field", value: "2" });
  }
  return rows;
}

function inferFieldName(kind) {
  const task = $("taskText").value || "";
  const common = task.match(/\b([A-Za-z_][A-Za-z0-9_]{1,24})\b/);
  if (/(行政区划代码|区划代码|编码|代码|code)/i.test(task)) return "code";
  if (/(名称|乡镇|县|区|name)/i.test(task)) return "name";
  if (kind === "zone") return "id";
  return common?.[1] || "";
}

function renderLayerFieldMappings(workflow = state.lastWorkflow) {
  const box = $("layerFieldMappings");
  if (!box) return;
  const existing = {};
  box.querySelectorAll("[data-var-key]").forEach((input) => {
    const key = input.getAttribute("data-var-key");
    if (key && input.value.trim()) existing[key] = input.value.trim();
  });
  const rows = layerFieldRows(workflow);
  if (!rows.length) {
    box.innerHTML = `<div class="summary">当前流程没有检测到必须的图层/字段映射。遇到表连接、分区统计、可视域时，这里会显示要选择的图层和字段。</div>`;
    return;
  }
  box.innerHTML = `
    <div class="mapping-subtitle">图层与字段映射</div>
    <div class="summary">这里对应 QGIS/ArcGIS 工具参数里的“输入图层、连接表、连接字段、统计字段”。自动修复只能猜测；真实执行前需要确认。</div>
  `;
  for (const row of rows) {
    const value = existing[row.key] || row.value || "";
    const wrap = document.createElement("label");
    wrap.className = "mapping-row";
    if (row.type === "layer") {
      wrap.innerHTML = `
        <span>${parameterLabel(row.key)} *</span>
        <select data-var-key="${row.key}">${optionHtml(row.options || [], value)}</select>
        <input data-var-key="${row.key}" value="${value}" placeholder="${parameterPlaceholder(row.key)}" />
      `;
      const select = wrap.querySelector("select");
      const input = wrap.querySelector("input");
      select.addEventListener("change", () => {
        input.value = select.value;
      });
    } else {
      wrap.innerHTML = `
        <span>${parameterLabel(row.key)} *</span>
        <input data-var-key="${row.key}" value="${value}" placeholder="${parameterPlaceholder(row.key)}" />
      `;
    }
    box.appendChild(wrap);
  }
}

function autoRepairMappings() {
  if (!state.lastWorkflow) {
    setStatus("status.repairNoWorkflow", "warning");
    return;
  }
  renderVariableMappings(state.lastWorkflow);
  const repairItems = workflowParameterTokens(state.lastWorkflow).map((token) => {
    const input = document.querySelector(`[data-var-key="${token}"]`);
    return {
      key: token,
      label: parameterLabel(token),
      value: input?.value?.trim() || "",
      guessed: isGuessedParameter(token, input?.value?.trim() || ""),
    };
  });
  renderRepairFeedback(repairItems);
  renderLayerFieldMappings(state.lastWorkflow);
  setStatus("status.repairDone", "ok");
}

function renderProcessStatus(rows = [], outputDir = "") {
  const box = $("processStatus");
  box.innerHTML = "";
  if (!rows.length) {
    box.innerHTML = `<div class="summary warning">${t("summary.noProgress")}</div>`;
    return;
  }
  const header = document.createElement("div");
  header.className = "process-header";
  const problemCount = rows.filter((row) => row.status === "blocked" || row.status === "failed").length;
  header.textContent = outputDir ? `输出目录：${outputDir}` : "执行进度";
  box.appendChild(header);
  if (problemCount) {
    const tokens = unresolvedTokensFromRows(rows);
    const summary = document.createElement("div");
    summary.className = "blocking-summary";
    summary.innerHTML = `
      <strong>优先处理 ${problemCount} 个阻塞/失败步骤</strong>
      <span>${tokens.length ? `缺少：${tokens.map(parameterLabel).join("、")}` : "请先查看下方红色步骤提示。"}</span>
      <button id="focusBlockedBtn">定位需要填写的参数</button>
    `;
    box.appendChild(summary);
  }
  const sortedRows = [...rows].sort((a, b) => statusPriority(a.status) - statusPriority(b.status));
  for (const row of sortedRows) {
    const item = document.createElement("div");
    item.className = `process-item ${row.status}`;
    const outputs = row.outputs?.filter(Boolean)?.length ? row.outputs.filter(Boolean).join(" | ") : "无输出文件";
    const actionHint = row.status === "blocked" || row.status === "failed"
      ? `<div class="action-hint">${row.message || "此步骤缺少参数或执行失败。请按提示补齐后重新预览。"}</div>`
      : `<div class="hint">${row.message || "步骤状态已更新"}</div>`;
    item.innerHTML = `
      <div class="process-title">
        <strong>${row.step_id}</strong>
        <span>${processLabel(row.status)}</span>
      </div>
      ${actionHint}
      <div class="hint">输出：${outputs}</div>
      <button class="step-action" data-step-id="${row.step_id}">从此步回溯 / 重跑（待接入）</button>
    `;
    box.appendChild(item);
  }
  const tokens = highlightMissingMappings(rows);
  const focusButton = $("focusBlockedBtn");
  if (focusButton) {
    focusButton.addEventListener("click", () => {
      const first = tokens.map((token) => document.querySelector(`[data-var-key="${token}"]`)).find(Boolean);
      if (first) {
        first.scrollIntoView({ block: "center", behavior: "smooth" });
        first.focus();
        setStatus(`已定位到需要补充的参数：${parameterLabel(first.getAttribute("data-var-key"))}`, "warning", true);
      }
    });
  }
  box.querySelectorAll(".step-action").forEach((btn) => {
    btn.addEventListener("click", () => {
      setStatus(`已选中回溯起点：${btn.getAttribute("data-step-id")}。局部重跑执行器尚未接入。`, "warning", true);
    });
  });
}

function renderOperationModules(modules = []) {
  const box = $("operationModules");
  box.innerHTML = "";
  if (!modules.length) {
    box.innerHTML = `<div class="summary warning">${t("summary.modulesIdle")}</div>`;
    return;
  }
  const sortedModules = [...modules].sort((a, b) => statusPriority(a.status) - statusPriority(b.status));
  for (const module of sortedModules) {
    const card = document.createElement("div");
    card.className = `module-card ${module.status}`;
    const inputs = (module.inputs || []).slice(0, 6).map((item) => `<li>${item}</li>`).join("");
    const steps = (module.steps || []).map((item) => `<li>${item}</li>`).join("");
    const checks = (module.checks || []).slice(0, 4).map((item) => `<li>${item}</li>`).join("");
    const blockers = (module.blockers || []).map((item) => `<li>${item}</li>`).join("");
    const backend = (module.backend || []).join(" / ");
    card.innerHTML = `
      <div class="module-title">
        <strong>${module.title}</strong>
        <span class="tag">${moduleStatusLabel(module.status)}</span>
      </div>
      <div class="hint">类别：${module.category || module.data_group || ""}${backend ? ` | 后端：${backend}` : ""}</div>
      ${inputs ? `<div class="hint">已识别输入</div><ul class="module-list">${inputs}</ul>` : ""}
      ${steps ? `<div class="hint">处理链</div><ul class="module-list">${steps}</ul>` : ""}
      ${checks ? `<div class="hint">必检点</div><ul class="module-list">${checks}</ul>` : ""}
      ${blockers ? `<div class="hint">阻塞/需确认</div><ul class="module-list">${blockers}</ul>` : ""}
    `;
    box.appendChild(card);
  }
}

async function refreshOperationModules() {
  if (!state.lastScan) {
    renderOperationModules([]);
    return;
  }
  try {
    const payload = await api("/api/operation-modules", {
      method: "POST",
      body: JSON.stringify({
        task: $("taskText").value.trim(),
        scan: state.lastScan,
        analysis: state.lastAnalysis || {},
      }),
    });
    renderOperationModules(payload.modules || []);
  } catch (error) {
    console.warn(error);
  }
}

function renderHistory(history) {
  const projects = $("recentProjects");
  projects.innerHTML = "";
  const recent = history.recent_projects || [];
  if (!recent.length) {
    projects.innerHTML = `<div class="hint">暂无最近项目。</div>`;
  } else {
    for (const item of recent.slice(0, 6)) {
      const btn = document.createElement("button");
      btn.className = "recent-item";
      btn.innerHTML = `
        <strong>${item.folder || "未命名项目"}</strong>
        <small>${item.last_opened || ""}</small>
      `;
      btn.addEventListener("click", () => restoreProject(item));
      projects.appendChild(btn);
    }
  }

  const runs = $("runHistory");
  runs.innerHTML = "";
  const visibleRuns = (history.runs || []).filter((run) => run.workflow !== "first_hunan_competition");
  for (const run of visibleRuns.slice(0, 5)) {
    const row = document.createElement("button");
    row.className = "run-item";
    const s = run.summary || {};
    row.innerHTML = `
      <strong>${run.time} - ${run.dry_run ? "预览" : "执行"}</strong>
      <small>${run.workflow || ""} - 阻塞 ${s.blocked || 0}，失败 ${s.failed || 0}，完成 ${s.completed || 0}</small>
    `;
    row.addEventListener("click", () => {
      renderProcessStatus(run.results || [], run.output_dir || "");
      log(run);
      setStatus("status.historyRunRestored", "ok");
    });
    runs.appendChild(row);
  }
}

function renderAnalysis(analysis) {
  const box = $("analysisBox");
  const guidance = analysis.guidance || null;
  const formulaInterpretation = analysis.llm?.analysis?.formula_interpretation || analysis.formula_interpretation || [];
  const trainingMatches = (analysis.training_matches || [])
    .map((item) => `<li>${Math.round((item.score || 0) * 100)}% - ${item.file}：${item.title}<br><span>${item.snippet || ""}</span></li>`)
    .join("");
  const formulas = formulaInterpretation
    .map((item, index) => {
      const fields = (item.needed_fields || []).map((field) => `<li>${field}</li>`).join("");
      const steps = (item.gis_steps || []).map((step) => `<li>${step}</li>`).join("");
      const checks = (item.checks || []).map((check) => `<li>${check}</li>`).join("");
      return `
        <div class="formula-card">
          <strong>${index + 1}. ${item.formula || "公式/计算关系"}</strong>
          ${item.meaning ? `<p>${item.meaning}</p>` : ""}
          ${fields ? `<div class="hint">需要字段</div><ul>${fields}</ul>` : ""}
          ${steps ? `<div class="hint">GIS 处理步骤</div><ul>${steps}</ul>` : ""}
          ${checks ? `<div class="hint">检查点</div><ul>${checks}</ul>` : ""}
        </div>
      `;
    })
    .join("");
  if (guidance) {
    const evidence = (guidance.evidence || []).map((item) => `<li>${item}</li>`).join("");
    const dataRoles = (guidance.data_roles || []).map((item) => `<li>${item}</li>`).join("");
    const uncertain = (guidance.missing_or_uncertain || []).map((item) => `<li>${item}</li>`).join("");
    const checks = (guidance.result_checks || []).map((item) => `<li>${item}</li>`).join("");
    const memories = (guidance.similar_memory || [])
      .map((item) => `<li>${Math.round((item.score || 0) * 100)}% - ${item.task}<br><span>${item.usable || ""}</span></li>`)
      .join("");
    const route = (guidance.recommended_route || [])
      .map((step, index) => {
        const params = (step.route?.parameters || []).map((item) => `<li>${item}</li>`).join("");
        const stepChecks = (step.route?.checks || []).map((item) => `<li>${item}</li>`).join("");
        return `
          <div class="guidance-step">
            <div class="step-title">
              <span>${index + 1}. ${step.title}</span>
              <span class="tag">${step.route?.automation || "指导"}</span>
            </div>
            <p>${step.purpose || ""}</p>
            <div class="reason">${step.reason || ""}</div>
            <div class="software-route"><strong>ArcGIS Pro：</strong>${step.route?.arcgis_pro || "待补充"}</div>
            <div class="software-route"><strong>QGIS 替代：</strong>${step.route?.qgis || "待补充"}</div>
            ${params ? `<div class="hint">关键参数</div><ul>${params}</ul>` : ""}
            ${stepChecks ? `<div class="hint">检查标准</div><ul>${stepChecks}</ul>` : ""}
            ${step.risk ? `<div class="action-hint">${step.risk}</div>` : ""}
            ${step.user_action ? `<div class="hint">${step.user_action}</div>` : ""}
          </div>
        `;
      })
      .join("");
    box.innerHTML = `
      <div class="analysis-card guidance-card">
        <strong>题目分析：${guidance.task_category || "未分类"}</strong>
        <p>${guidance.orientation || ""}。${guidance.analysis_mode || ""}</p>
        <p>${guidance.goal || ""}</p>
        ${evidence ? `<h4>判断依据</h4><ul>${evidence}</ul>` : ""}
        ${dataRoles ? `<h4>已识别数据</h4><ul>${dataRoles}</ul>` : ""}
        ${uncertain ? `<h4>缺失或需确认</h4><ul>${uncertain}</ul>` : ""}
        ${formulas ? `<h4>公式与计算关系</h4>${formulas}` : ""}
        ${route ? `<h4>推荐操作路线</h4>${route}` : ""}
        ${checks ? `<h4>结果检查清单</h4><ul>${checks}</ul>` : ""}
        ${trainingMatches ? `<h4>训练反思匹配</h4><ul>${trainingMatches}</ul>` : ""}
        ${memories ? `<h4>相似训练记忆</h4><ul>${memories}</ul>` : ""}
        <div class="action-hint">${guidance.execution_policy || ""}</div>
      </div>
    `;
    return;
  }
  const ops = (analysis.operations || [])
    .slice(0, 10)
    .map((item) => `<li>${item.name} <span>${Math.round(item.confidence * 100)}%</span></li>`)
    .join("");
  const missing = (analysis.missing_conditions || []).map((item) => `<li>${item}</li>`).join("");
  const risks = (analysis.risks || []).slice(0, 6).map((item) => `<li>${item}</li>`).join("");
  const cases = (analysis.similar_cases || []).map((item) => `<li>${Math.round(item.score * 100)}% - ${item.task}</li>`).join("");
  box.innerHTML = `
    <div class="analysis-card">
      <strong>AI/规则分析：${analysis.task_types?.join(", ") || "unknown"} - 置信度 ${Math.round((analysis.confidence || 0) * 100)}%</strong>
      <p>${analysis.summary || ""}</p>
      ${ops ? `<h4>候选操作</h4><ul>${ops}</ul>` : ""}
      ${formulas ? `<h4>公式与计算关系</h4>${formulas}` : ""}
      ${missing ? `<h4>缺失条件</h4><ul>${missing}</ul>` : ""}
      ${risks ? `<h4>风险提醒</h4><ul>${risks}</ul>` : ""}
      ${trainingMatches ? `<h4>训练反思匹配</h4><ul>${trainingMatches}</ul>` : ""}
      ${cases ? `<h4>相似记忆</h4><ul>${cases}</ul>` : ""}
    </div>
  `;
}

function restoreProject(item) {
  $("folderPath").value = item.folder || "";
  $("taskText").value = item.task || "";
  $("dataPath").value = item.main_data || "";
  if (item.workflow) $("workflowName").value = item.workflow;
  if (item.output_dir) $("outputDir").value = item.output_dir;
  state.selectedPaths.main = item.main_data || "";
  state.selectedPaths.mainRole = "";
  setStatus("status.historyRestored", "ok");
}

async function refreshHistory() {
  try {
    const history = await api("/api/history");
    renderHistory(history);
  } catch (error) {
    console.warn(error);
  }
}

async function loadProviders() {
  try {
    const payload = await api("/api/ai/providers");
    const providers = payload.providers || {};
    const selected = $("aiProvider").value || "deepseek";
    const cfg = providers[selected];
    if (cfg?.model && !$("aiModel").value.trim()) $("aiModel").value = cfg.model;
    const keyStatus = $("aiKeyStatus");
    if (!keyStatus) return;
    if (selected === "local") {
      keyStatus.className = "summary ok";
      keyStatus.textContent = "当前使用本地规则，不需要 API Key。";
      return;
    }
    if (cfg?.has_key) {
      keyStatus.className = "summary ok";
      keyStatus.textContent = `API Key 已设置：${cfg.api_key_env}，模型：${$("aiModel").value || cfg.model}`;
    } else {
      keyStatus.className = "summary warning";
      keyStatus.textContent = `API Key 未设置：请在启动服务前设置 ${cfg?.api_key_env || "API_KEY"}。`;
    }
  } catch (error) {
    console.warn(error);
  }
}

function applyModelPreset() {
  const preset = $("modelPreset").value;
  if (preset !== "custom") $("aiModel").value = preset;
  loadProviders();
}

function hasUnresolved(step) {
  const text = JSON.stringify(step);
  return text.includes("threshold") || text.includes("<") || text.includes(">");
}

function statusLabel(status) {
  const labels = {
    pending: "需人工确认",
    ready: "可预览",
    blocked: "缺参数",
    failed: "失败",
    completed: "已完成",
    dry_run: "已预览",
    skipped: "已跳过",
  };
  return labels[status] || status;
}

function engineLabel(engine) {
  const labels = {
    qgis_processing: "QGIS 处理工具",
    whitebox: "WhiteboxTools",
    autogis: "本工具",
    pending: "人工/QGIS 指导",
  };
  return labels[engine] || engine;
}

function taskTypeLabel(type) {
  const labels = {
    hydrology: "水文分析",
    terrain: "地形分析",
    building_sunlight: "建筑日照/阴影",
    site_selection: "选址/约束筛选",
    viewshed: "可视域分析",
    reclass_change: "重分类/变化分析",
    zonal_statistics: "分区统计",
    attribute_join: "属性表连接",
    vector_edit_geometry: "要素编辑/几何处理",
    formula_indicators: "公式/指标计算",
    unknown: "未明确分类",
  };
  return labels[type] || type;
}

function classifyStep(step) {
  if (step.engine === "pending") return "pending";
  if (hasUnresolved(step)) return "blocked";
  return "ready";
}

function renderWorkflow(workflow) {
  state.lastWorkflow = workflow;
  renderVariableMappings(workflow);
  renderLayerFieldMappings(workflow);
  const missing = workflow.missing_inputs?.length ? `缺失条件：${workflow.missing_inputs.join("; ")}` : "缺失条件：无";
  const level = workflow.missing_inputs?.length ? "warning" : "ok";
  $("workflowSummary").className = `summary ${level}`;
  $("workflowSummary").textContent = `任务类型：${(workflow.task_types || []).map(taskTypeLabel).join("、")}。${missing}`;
  renderProcessStatus();
  $("flowList").innerHTML = "";
  const sortedSteps = [...(workflow.steps || [])].sort((a, b) => statusPriority(classifyStep(a)) - statusPriority(classifyStep(b)));
  for (const step of sortedSteps) {
    const status = classifyStep(step);
    const outputs = step.outputs ? Object.values(step.outputs).join(", ") : "";
    const node = document.createElement("div");
    node.className = `step ${status}`;
    node.innerHTML = `
      <div class="step-title">
        <span>${step.id} - ${step.title}</span>
        <span class="tag">${statusLabel(status)}</span>
      </div>
      <div>${step.purpose}</div>
      <div class="hint">算法：${step.algorithm} | 引擎：${engineLabel(step.engine)}</div>
      ${outputs ? `<div class="hint">预计输出：${outputs}</div>` : ""}
      ${step.checks?.length ? `<div class="hint">检查：${step.checks.join("; ")}</div>` : ""}
    `;
    $("flowList").appendChild(node);
  }
}

function renderStatCheck(payload) {
  const box = $("statCheckBox");
  if (!box) return;
  const results = payload.results || [];
  if (!results.length) {
    box.innerHTML = `<div class="summary warning">没有可显示的统计核查结果。</div>`;
    return;
  }
  box.innerHTML = "";
  for (const result of results) {
    const card = document.createElement("div");
    card.className = "stat-card";
    if (!result.ok) {
      card.innerHTML = `<strong>${result.path || "表格"}</strong><div class="action-hint">${result.error || "读取失败"}</div>`;
      box.appendChild(card);
      continue;
    }
    const numeric = (result.numeric_summary || [])
      .slice(0, 6)
      .map((item) => `<li>${item.column}：均值 ${item.mean ?? "-"}，最小 ${item.min ?? "-"}，最大 ${item.max ?? "-"}</li>`)
      .join("");
    const hints = (result.formula_hints || []).map((item) => `<li>${item}</li>`).join("");
    const warnings = (result.warnings || []).map((item) => `<li>${item}</li>`).join("");
    const nulls = Object.entries(result.null_counts || {})
      .slice(0, 8)
      .map(([key, value]) => `<li>${key}：${value}</li>`)
      .join("");
    card.innerHTML = `
      <strong>${result.name}</strong>
      <div class="hint">${result.rows} 行，${(result.columns || []).length} 列。重复行：${result.duplicate_rows || 0}</div>
      ${hints ? `<div class="hint">公式/题目核查建议</div><ul>${hints}</ul>` : ""}
      ${warnings ? `<div class="action-hint"><ul>${warnings}</ul></div>` : ""}
      ${nulls ? `<div class="hint">空值字段</div><ul>${nulls}</ul>` : ""}
      ${numeric ? `<div class="hint">数值字段摘要</div><ul>${numeric}</ul>` : ""}
      ${result.chart_path ? `<div class="hint">图表已生成：${result.chart_path}</div>` : ""}
    `;
    box.appendChild(card);
  }
}

function renderScan(scan) {
  state.lastScan = scan;
  const counts = scan.counts || {};
  const hasData = (counts.dem || 0) + (counts.raster || 0) + (counts.vector || 0) + (counts.boundary || 0) > 0;
  $("scanSummary").className = `summary ${hasData ? "ok" : "warning"}`;
  $("scanSummary").textContent = `扫描完成：共 ${counts.total || 0} 个可用数据/文档项。DEM ${counts.dem || 0}，栅格 ${counts.raster || 0}，矢量 ${counts.vector || 0}，题目 ${counts.question || 0}。`;
  $("scanList").innerHTML = "";

  const groups = scan.groups || {};
  const roleOrder = ["question", "dem", "boundary", "remote_sensing", "hydro_vector", "raster", "vector", "table", "document", "other"];
  for (const role of roleOrder) {
    const items = groups[role] || [];
    if (!items.length) continue;
    const block = document.createElement("div");
    block.className = "scan-group";
    block.innerHTML = `<h3>${roleLabel(role)} <span>${items.length}</span></h3>`;
    for (const item of items.slice(0, 16)) {
      const row = document.createElement("button");
      row.className = `file-row role-${role}`;
      row.title = item.path;
      const preview = item.preview ? `${item.preview.slice(0, 260)}${item.preview.length > 260 ? "..." : ""}` : "";
      row.innerHTML = `
        <div class="file-head">
          <strong>${item.name}</strong>
          <span class="role-badge">${roleLabel(item.role)}</span>
        </div>
        <small>${item.kind} | ${Math.round(item.confidence * 100)}% | ${item.reason}</small>
        ${preview ? `<p>${preview}</p>` : ""}
      `;
      row.addEventListener("click", () => chooseFile(item));
      block.appendChild(row);
    }
    $("scanList").appendChild(block);
  }
  refreshOperationModules();
  renderLayerFieldMappings();
}

function chooseFile(item) {
  if (item.role === "question") {
    state.selectedQuestion = item.path;
    if (item.preview) {
      $("taskText").value = item.preview;
      setStatus(`已从 ${item.name} 提取题目文本。`, "ok", true);
      return;
    }
    setStatus(`已选择题目文档：${item.name}。当前未提取到正文，请手动复制题目。`, "warning", true);
    return;
  }
  $("dataPath").value = item.path;
  state.selectedPaths.main = item.path;
  state.selectedPaths.mainRole = item.role || "";
  if (item.role === "dem") state.selectedPaths.DEM = item.path;
  renderVariableMappings();
  renderLayerFieldMappings();
  setStatus(`已选择 ${roleLabel(item.role)}：${item.name}。`, "ok", true);
}

function applySuggestedScan() {
  const scan = state.lastScan;
  if (!scan?.suggested) {
    setStatus("status.noScan", "warning");
    return;
  }
  const suggested = scan.suggested;
  if (suggested.task_text && !$("taskText").value.trim()) $("taskText").value = suggested.task_text;
  if (suggested.question) state.selectedQuestion = suggested.question;
  const data = suggested.dem || suggested.primary_raster || suggested.primary_vector || "";
  if (data) {
    $("dataPath").value = data;
    state.selectedPaths.main = data;
    state.selectedPaths.DEM = suggested.dem || "";
    state.selectedPaths.mainRole = suggested.dem === data ? "dem" : "";
  }
  renderVariableMappings();
  renderLayerFieldMappings();
  setStatus(data ? "status.suggestApplied" : "status.noSuggestedData", data ? "ok" : "warning");
}

function collectDataPath() {
  const path = $("dataPath").value.trim();
  return path ? [path] : [];
}

function collectTablePaths() {
  const groups = state.lastScan?.groups || {};
  const paths = [];
  for (const item of groups.table || []) {
    if (item.path) paths.push(item.path);
  }
  const main = $("dataPath").value.trim();
  if (main && /\.(csv|xlsx|xls)$/i.test(main)) paths.push(main);
  return [...new Set(paths)];
}

function collectVariables() {
  const variables = {};
  document.querySelectorAll("[data-var-key]").forEach((input) => {
    const key = input.getAttribute("data-var-key");
    const value = input.value.trim();
    if (key && value) {
      variables[key] = value;
      variables[key.toUpperCase()] = value;
      variables[key.toLowerCase()] = value;
    }
  });
  if (variables.MAIN && !variables.DEM && workflowNeedsToken(state.lastWorkflow, "<DEM>")) {
    variables.DEM = variables.MAIN;
  }
  return variables;
}

function validateBeforePlan() {
  if (!$("taskText").value.trim()) {
    setStatus("status.questionRequired", "warning");
    return false;
  }
  if (!$("dataPath").value.trim()) {
    setStatus("status.dataRequired", "warning");
    return false;
  }
  return true;
}

async function initialize() {
  await loadLocale();
  syncOutputDir();
  renderVariableMappings(null);
  renderLayerFieldMappings(null);
  renderProcessStatus();
  await refreshHistory();
  await loadProviders();
  try {
    const result = await api("/api/doctor");
    log(result);
    setStatus("status.ready", "ok");
  } catch (error) {
    log(String(error));
    setStatus("status.doctorFailed", "error");
  }
}

$("doctorBtn").addEventListener("click", async () => {
  try {
    setBusy(true, "status.doctorRunning");
    const result = await api("/api/doctor");
    log(result);
    setStatus("status.doctorDone", "ok");
  } catch (error) {
    log(String(error));
    setStatus("status.doctorFailed", "error");
  } finally {
    setBusy(false);
  }
});

$("scanFolderBtn").addEventListener("click", async () => {
  try {
    const path = $("folderPath").value.trim();
    if (!path) {
      setStatus("status.folderRequired", "warning");
      return;
    }
    setBusy(true, "status.scanning");
    const scan = await api("/api/scan-folder", {
      method: "POST",
      body: JSON.stringify({ path, max_files: 500 }),
    });
    renderScan(scan);
    applySuggestedScan();
    refreshHistory();
    log(scan);
  } catch (error) {
    log(String(error));
    setStatus("status.scanFailed", "error");
  } finally {
    setBusy(false);
  }
});

$("inspectBtn").addEventListener("click", async () => {
  try {
    const path = $("dataPath").value.trim();
    if (!path) {
      setStatus("status.dataRequired", "warning");
      return;
    }
    setBusy(true, "status.inspectRunning");
    const result = await api("/api/inspect", { method: "POST", body: JSON.stringify({ path }) });
    log(result);
    setStatus(result.ok ? "status.inspectDone" : "status.inspectWarn", result.ok ? "ok" : "warning");
  } catch (error) {
    log(String(error));
    setStatus("status.inspectFailed", "error");
  } finally {
    setBusy(false);
  }
});

$("clearDataBtn").addEventListener("click", () => {
  $("folderPath").value = "";
  $("dataPath").value = "";
  $("taskText").value = "";
  state.selectedPaths = { main: "", DEM: "", mainRole: "" };
  state.selectedQuestion = "";
  renderVariableMappings(null);
  renderLayerFieldMappings(null);
  $("scanSummary").className = "summary warning";
  $("scanSummary").textContent = t("summary.scanIdle");
  $("scanList").innerHTML = "";
    state.lastScan = null;
    state.lastAnalysis = null;
    setStatus("status.cleared", "info");
});

$("useSuggestedBtn").addEventListener("click", applySuggestedScan);
$("resultRoot").addEventListener("input", syncOutputDir);
$("runName").addEventListener("input", syncOutputDir);

$("analyzeBtn").addEventListener("click", async () => {
  let waitTimer = null;
  try {
    if (!$("taskText").value.trim()) {
      setStatus("status.questionRequired", "warning");
      return;
    }
    setBusy(true, "status.analyzing");
    waitTimer = window.setTimeout(() => setStatus("status.aiWaiting", "warning"), 15000);
    const analysis = await api("/api/analyze-task", {
      method: "POST",
      body: JSON.stringify({
        task: $("taskText").value.trim(),
        scan: state.lastScan || {},
        provider: $("aiProvider").value,
        model: $("aiModel").value.trim(),
      }),
    });
    state.lastAnalysis = analysis;
    renderAnalysis(analysis);
    refreshOperationModules();
    log(analysis);
    setStatus("status.analyzeDone", analysis.missing_conditions?.length ? "warning" : "ok");
  } catch (error) {
    log(String(error));
    setStatus("status.analyzeFailed", "error");
  } finally {
    if (waitTimer) window.clearTimeout(waitTimer);
    setBusy(false);
  }
});

$("planBtn").addEventListener("click", async () => {
  try {
    if (!validateBeforePlan()) return;
    syncOutputDir();
    setBusy(true, "status.planRunning");
    state.workflowName = $("workflowName").value.trim() || "web_workflow.json";
    const workflow = await api("/api/plan", {
      method: "POST",
      body: JSON.stringify({
        task: $("taskText").value.trim(),
        data: collectDataPath(),
        scan: state.lastScan || {},
        provider: $("aiProvider").value,
        model: $("aiModel").value.trim(),
        save_name: state.workflowName,
        folder: $("folderPath").value.trim(),
        output_dir: $("outputDir").value.trim(),
        analysis: state.lastAnalysis || {},
      }),
    });
    renderWorkflow(workflow);
    log(workflow);
    setStatus("status.planDone", workflow.missing_inputs?.length ? "warning" : "ok");
  } catch (error) {
    log(String(error));
    setStatus("status.planFailed", "error");
  } finally {
    setBusy(false);
  }
});

async function execute(dryRun) {
  if (!state.lastWorkflow) {
    setStatus("status.planRequired", "warning", true);
    return;
  }
  autoRepairMappings();
  syncOutputDir();
  if (!dryRun && !confirm(t("status.confirmRun"))) return;
  try {
    setBusy(true, dryRun ? "status.previewRunning" : "status.runRunning");
    const result = await api("/api/execute", {
      method: "POST",
      body: JSON.stringify({
        workflow: state.workflowName,
        variables: collectVariables(),
        output_dir: $("outputDir").value.trim(),
        task: $("taskText").value.trim(),
        folder: $("folderPath").value.trim(),
        main_data: $("dataPath").value.trim(),
        dry_run: dryRun,
      }),
    });
    log(result);
    const rows = result.results || [];
    renderProcessStatus(rows, result.output_dir || $("outputDir").value);
    refreshHistory();
    const blocked = rows.filter((item) => item.status === "blocked" || item.status === "failed");
    setStatus(
      blocked.length
        ? `存在 ${blocked.length} 个阻塞/失败步骤，请查看中间状态和日志。`
        : `完成。结果目标：${$("outputDir").value}`,
      blocked.length ? "warning" : "ok",
      true,
    );
  } catch (error) {
    log(String(error));
    setStatus("status.executeFailed", "error");
  } finally {
    setBusy(false);
  }
}

$("dryRunBtn").addEventListener("click", () => execute(true));
$("runBtn").addEventListener("click", () => execute(false));
$("repairBtn").addEventListener("click", autoRepairMappings);
$("statCheckBtn").addEventListener("click", async () => {
  const paths = collectTablePaths();
  if (!paths.length) {
    setStatus("status.statCheckNoTable", "warning");
    return;
  }
  try {
    setBusy(true, "status.statCheckRunning");
    const result = await api("/api/stat-check", {
      method: "POST",
      body: JSON.stringify({
        paths,
        task: $("taskText").value.trim(),
        output_dir: $("outputDir").value.trim() || $("resultRoot").value.trim(),
      }),
    });
    renderStatCheck(result);
    log(result);
    setStatus("status.statCheckDone", "ok");
  } catch (error) {
    log(String(error));
    setStatus("status.statCheckFailed", "error");
  } finally {
    setBusy(false);
  }
});
$("helpBtn").addEventListener("click", () => $("helpPanel").classList.remove("hidden"));
$("closeHelpBtn").addEventListener("click", () => $("helpPanel").classList.add("hidden"));
$("toggleAiConfigBtn").addEventListener("click", () => {
  $("aiConfigPanel").classList.toggle("hidden");
  loadProviders();
});
$("rebuildTrainingBtn").addEventListener("click", async () => {
  try {
    setBusy(true, "status.trainingRebuildRunning");
    const result = await api("/api/rebuild-training-index", { method: "POST", body: JSON.stringify({}) });
    log(result);
    setStatus(`训练反思索引已重建：${result.count || 0} 条。`, "ok", true);
  } catch (error) {
    log(String(error));
    setStatus("status.trainingRebuildFailed", "error");
  } finally {
    setBusy(false);
  }
});
$("aiProvider").addEventListener("change", () => {
  const provider = $("aiProvider").value;
  if (provider === "deepseek") {
    $("modelPreset").value = "deepseek-v4-pro";
    $("aiModel").value = "deepseek-v4-pro";
  } else if (provider === "openai") {
    $("modelPreset").value = "gpt-4.1-mini";
    $("aiModel").value = "gpt-4.1-mini";
  }
  loadProviders();
});
$("modelPreset").addEventListener("change", applyModelPreset);
$("aiModel").addEventListener("input", () => {
  $("modelPreset").value = "custom";
  loadProviders();
});
$("dropZone").addEventListener("dragover", (event) => {
  event.preventDefault();
  $("dropZone").classList.add("dragging");
});
$("dropZone").addEventListener("dragleave", () => $("dropZone").classList.remove("dragging"));
$("dropZone").addEventListener("drop", (event) => {
  event.preventDefault();
  $("dropZone").classList.remove("dragging");
  setStatus("status.dropUnsupported", "warning");
});

initialize();
