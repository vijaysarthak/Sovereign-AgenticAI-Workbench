/**
 * SEVERANCE Client Application Logic
 */

async function fetchAPI(url, options = {}) {
  const defaultOptions = {
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "same-origin",
  };

  const merged = {
    ...defaultOptions,
    ...options,
    headers: {
      ...defaultOptions.headers,
      ...(options.headers || {}),
    },
  };

  const res = await fetch(url, merged);
  if (res.status === 401 && !url.includes("/auth/login")) {
    window.location.href = "/login";
    throw new Error("Session expired. Please log in.");
  }
  return res;
}

async function getCurrentPrincipal() {
  try {
    const res = await fetchAPI("/me");
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.error("Auth check failed:", err);
  }
  return null;
}

async function doLogout() {
  try {
    await fetchAPI("/auth/logout", { method: "POST" });
  } finally {
    window.location.href = "/login";
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Minimal, dependency-free Markdown -> HTML renderer.
 * Input is always HTML-escaped first, so no raw HTML from the source
 * text (e.g. an LLM answer) can inject markup or scripts.
 */
function renderMarkdown(source) {
  const escaped = escapeHtml(source || "");

  // Inline formatting: bold, italic, inline code
  const inline = (text) => text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");

  const lines = escaped.split(/\r?\n/);
  const htmlParts = [];
  let listBuffer = [];
  let listType = null;

  const flushList = () => {
    if (listBuffer.length > 0) {
      htmlParts.push(`<${listType}>${listBuffer.join("")}</${listType}>`);
      listBuffer = [];
      listType = null;
    }
  };

  for (const rawLine of lines) {
    // Strip leading Markdown blockquote markers ("> ", possibly repeated/nested)
    // so a line like "> ## Heading" is still recognized as a heading rather than
    // falling through to a literal, unrendered paragraph. Matches against the
    // already-HTML-escaped text, so ">" here is "&gt;".
    const line = rawLine.trim().replace(/^(?:&gt;\s*)+/, "");

    if (line === "") {
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushList();
      const level = headingMatch[1].length;
      htmlParts.push(`<h${level}>${inline(headingMatch[2])}</h${level}>`);
      continue;
    }

    const ulMatch = line.match(/^[-*]\s+(.*)$/);
    const olMatch = line.match(/^\d+\.\s+(.*)$/);
    if (ulMatch) {
      if (listType !== "ul") { flushList(); listType = "ul"; }
      listBuffer.push(`<li>${inline(ulMatch[1])}</li>`);
      continue;
    }
    if (olMatch) {
      if (listType !== "ol") { flushList(); listType = "ol"; }
      listBuffer.push(`<li>${inline(olMatch[1])}</li>`);
      continue;
    }

    flushList();
    htmlParts.push(`<p>${inline(line)}</p>`);
  }
  flushList();

  return htmlParts.join("");
}

function renderUserChip(principal, containerId = "userChipContainer") {
  const container = document.getElementById(containerId);
  if (!container || !principal) return;

  const comps = principal.compartments && principal.compartments.length > 0
    ? principal.compartments.join(", ")
    : "none";

  container.innerHTML = `
    <div class="user-chip">
      <div class="user-info">
        <div class="user-name">${principal.name} (${principal.job_title})</div>
        <div class="user-grade">Grade ${principal.grade} // Compartments: [${comps}]</div>
      </div>
      <button onclick="doLogout()">Sign Out</button>
    </div>
  `;
}
