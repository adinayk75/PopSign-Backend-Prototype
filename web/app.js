const state = {
  story: null,
  pageIndex: 0,
  currentView: "generate",
  difficulty: "Level A",
  backend: null,
};

const views = ["generate", "library", "cover", "reader"];
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function showView(name) {
  state.currentView = name;
  views.forEach((view) => {
    $(`#${view}-view`).classList.toggle("active", view === name);
  });
  $$(".bottom-nav button").forEach((button) => {
    const navView = button.dataset.view;
    const active = ["generate", "library", "cover", "reader"].includes(name) && navView === "library";
    button.classList.toggle("active", active);
  });
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

async function checkBackend() {
  const dot = $("#api-status-dot");
  try {
    const health = await requestJson("/api/health");
    state.backend = health;
    dot.classList.add("online");
    $("#api-status").textContent = `${health.data_backend} · ${health.dimensions}-D vectors`;
    $("#desktop-backend").textContent = `${health.data_backend} vector store`;
    $("#desktop-model").textContent = `${health.embedding_model}@${health.embedding_version}`;
  } catch (error) {
    $("#api-status").textContent = "Backend unavailable";
    $("#desktop-backend").textContent = "Offline";
    $("#desktop-model").textContent = error.message;
  }
}

function renderLibrary() {
  const grid = $("#book-grid");
  const story = state.story;
  const cards = [
    story && {
      title: story.title,
      author: story.author,
      image: story.cover,
      enabled: true,
    },
    {
      title: "My Cat",
      author: "Harley Hamilton",
      image: "/assets/cat-cover.svg",
      enabled: false,
    },
    {
      title: "Big Dog, Little Dog",
      author: "P. D. Eastman",
      image: "/assets/book-placeholder.svg",
      enabled: false,
    },
  ].filter(Boolean);

  grid.innerHTML = cards.map((card, index) => `
    <button class="book-card" type="button" data-book-index="${index}" ${card.enabled ? "" : "aria-label=\"Preview only\""}>
      <img src="${card.image}" alt="${card.title} cover" />
      <strong>${card.title}</strong>
      <small>${card.author}</small>
    </button>
  `).join("");

  $$(".book-card").forEach((card, index) => {
    card.addEventListener("click", () => {
      if (index === 0 && state.story) {
        renderCover();
        showView("cover");
      } else {
        showToast("Preview card — generate the demo story to open it.");
      }
    });
  });
}

function renderCover() {
  if (!state.story) return;
  $("#cover-title").textContent = state.story.title;
  $("#cover-art").src = state.story.cover;
  $("#cover-difficulty").textContent = state.story.difficulty;
  $("#cover-author").textContent = state.story.author;
}

function sentenceMarkup(sentence, activeWord) {
  return sentence.split(/(\s+)/).map((part) => {
    const normalized = part.toLowerCase().replace(/[^a-z0-9']/g, "");
    return normalized === activeWord ? `<span class="active-word">${part}</span>` : part;
  }).join("");
}

function renderWordChips(sentence, targetWord) {
  const words = sentence.match(/[A-Za-z0-9']+/g) || [];
  $("#word-chips").innerHTML = words.map((word) => {
    const normalized = word.toLowerCase();
    return `<button class="word-chip ${normalized === targetWord ? "active" : ""}" data-word="${normalized}" type="button">${word}</button>`;
  }).join("");

  $$(".word-chip").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.word === targetWord) {
        matchPage();
      } else {
        showToast(`“${button.textContent}” has one demo sign; “${targetWord}” is the ambiguous word.`);
      }
    });
  });
}

function setMatchLoading() {
  $("#decision-badge").textContent = "Matching…";
  $("#decision-badge").classList.remove("accepted");
  $("#sense-label").textContent = "Comparing phrase vectors";
  $("#sense-description").textContent = "Finding the closest stored examples for this word.";
  $("#video-key").textContent = "Waiting for match";
  $("#top-score").textContent = "—";
  $("#score-margin").textContent = "—";
}

async function matchPage() {
  if (!state.story) return;
  const page = state.story.pages[state.pageIndex];
  setMatchLoading();
  try {
    const result = await requestJson("/api/match", {
      method: "POST",
      body: JSON.stringify({ phrase: page.sentence, target_word: page.target_word }),
    });
    const accepted = result.accepted;
    const badge = $("#decision-badge");
    badge.textContent = accepted ? "Accepted" : "Needs review";
    badge.classList.toggle("accepted", accepted);
    $("#sense-label").textContent = result.recommended_sense || "No candidate found";
    $("#sense-description").textContent = result.candidates[0]?.definition || "No stored meaning could be compared.";
    $("#video-key").textContent = result.selected_video_key || `Review: ${result.recommended_video_key || "none"}`;
    $("#top-score").textContent = result.top_score.toFixed(3);
    $("#score-margin").textContent = result.margin.toFixed(3);
    $("#review-notice").textContent = `${result.review_notice} Threshold ${result.accept_threshold.toFixed(2)} + margin ${result.margin_threshold.toFixed(2)}.`;
  } catch (error) {
    $("#decision-badge").textContent = "Error";
    $("#sense-label").textContent = "Match unavailable";
    $("#sense-description").textContent = error.message;
  }
}

function renderReader() {
  if (!state.story) return;
  const page = state.story.pages[state.pageIndex];
  $("#page-number").textContent = `Page ${state.pageIndex + 1} / ${state.story.pages.length}`;
  $("#reader-title").textContent = state.story.title;
  $("#page-art").src = page.illustration;
  $("#page-art").alt = `Illustration for: ${page.sentence}`;
  $("#story-sentence").innerHTML = sentenceMarkup(page.sentence, page.target_word);
  $("#previous-page").disabled = state.pageIndex === 0;
  $("#next-page").disabled = state.pageIndex === state.story.pages.length - 1;
  renderWordChips(page.sentence, page.target_word);
  $("#sign-info-card").dataset.grammar = page.grammar;
  matchPage();
}

async function generateStory() {
  const button = $("#generate-button");
  button.disabled = true;
  button.textContent = "Generating…";
  try {
    state.story = await requestJson("/api/stories/demo", {
      method: "POST",
      body: JSON.stringify({
        prompt: $("#story-prompt").value,
        difficulty: state.difficulty,
      }),
    });
    state.pageIndex = 0;
    renderLibrary();
    showView("library");
    showToast("Story ready — open Maya Makes Dinner.");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Generate";
  }
}

function bindChoiceGroup(selector, callback) {
  $$(selector).forEach((button) => {
    button.addEventListener("click", () => {
      $$(selector).forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      callback(button.textContent.trim());
    });
  });
}

$("#generate-button").addEventListener("click", generateStory);
$("#start-learning").addEventListener("click", () => {
  state.pageIndex = 0;
  renderReader();
  showView("reader");
});
$("#previous-page").addEventListener("click", () => {
  if (state.pageIndex > 0) state.pageIndex -= 1;
  renderReader();
});
$("#next-page").addEventListener("click", () => {
  if (state.pageIndex < state.story.pages.length - 1) state.pageIndex += 1;
  renderReader();
});
$("#return-to-phrase").addEventListener("click", () => $("#story-sentence").scrollIntoView({ behavior: "smooth", block: "center" }));
$("#speed-slider").addEventListener("input", (event) => {
  $("#speed-label").textContent = `${Number(event.target.value).toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}×`;
});
$("#library-search").addEventListener("input", (event) => {
  const query = event.target.value.trim().toLowerCase();
  $$(".book-card").forEach((card) => {
    card.hidden = query && !card.textContent.toLowerCase().includes(query);
  });
});
$$(".segmented-control button").forEach((button) => {
  button.addEventListener("click", () => {
    $$(".segmented-control button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    if (button.textContent.trim() === "Explore") {
      showToast("Explore books are outside this prototype.");
    }
  });
});
$("#info-toggle").addEventListener("click", () => {
  $("#info-toggle").classList.add("active");
  $("#grammar-toggle").classList.remove("active");
  matchPage();
});
$("#grammar-toggle").addEventListener("click", () => {
  $("#grammar-toggle").classList.add("active");
  $("#info-toggle").classList.remove("active");
  $("#sense-label").textContent = "Grammar";
  $("#sense-description").textContent = $("#sign-info-card").dataset.grammar;
});

$$(".bottom-nav button").forEach((button) => {
  button.addEventListener("click", () => {
    const destination = button.dataset.view;
    if (destination === "generate") showView("generate");
    else if (destination === "library") {
      renderLibrary();
      showView("library");
    } else if (destination === "review" && state.story) {
      renderReader();
      showView("reader");
    } else {
      showToast(`${button.querySelector("small").textContent} is outside this prototype.`);
    }
  });
});

bindChoiceGroup("#theme-options .choice", () => {});
bindChoiceGroup("#difficulty-options .choice", (value) => { state.difficulty = value; });
renderLibrary();
checkBackend();
