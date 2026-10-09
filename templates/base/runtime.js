/* aside-shorts 런타임 — 모든 모션은 TL(멈춰 둔 GSAP 타임라인) 하나에 시각을 박아 넣는다.
 * 렌더러가 프레임마다 __seek(t) 로 그 시각을 찍는다 → 실시간 재생과 무관하게 언제나 같은 그림(결정론).
 *
 * 장면 스크립트에서 쓰는 것:
 *   SHORT             {duration, hook:{line1,line2}, cues:[{i,text,keywords,start,end}], images:{img1:{src,role,subject}}}
 *   TL                gsap.timeline({paused:true}) — 여기에만 트윈을 넣는다. 위치(초)를 꼭 준다.
 *   at(i, off=0)      i번 문장이 읽히기 시작하는 시각(+off초)
 *   end(i, off=0)     i번 문장이 끝나는 시각(+off초)
 *   IMG(key)          그림 경로 (img1 …)
 *   rand(seed)        0~1 결정론 난수
 */
(function () {
  window.__errors = [];
  window.addEventListener("error", function (e) { window.__errors.push(String(e.message || e)); });
  if (!window.gsap) { window.__errors.push("gsap 이 없습니다"); return; }
  var S = window.SHORT;
  var TL = gsap.timeline({ paused: true, defaults: { ease: "power3.out", duration: 0.6 } });
  window.TL = TL;
  window.at = function (i, off) { var c = S.cues[Math.max(0, Math.min(S.cues.length - 1, i))]; return Math.max(0, c.start + (off || 0)); };
  window.end = function (i, off) { var c = S.cues[Math.max(0, Math.min(S.cues.length - 1, i))]; return Math.max(0, c.end + (off || 0)); };
  window.IMG = function (k) { var m = S.images[k]; if (!m) { window.__errors.push("없는 그림 키: " + k); return ""; } return m.src; };
  window.rand = function (seed) { var x = Math.sin((seed + 1) * 9301.7) * 49297.3; return x - Math.floor(x); };

  // <img data-img="img1"> → src 채움, 다른 요소의 data-img → 배경 그림
  Array.prototype.forEach.call(document.querySelectorAll("[data-img]"), function (el) {
    var src = window.IMG(el.getAttribute("data-img"));
    if (el.tagName === "IMG") el.setAttribute("src", src);
    else el.style.backgroundImage = 'url("' + src + '")';
  });

  // 상단 후크 — 처음에 한 번 들어와서 끝까지 남는다
  var hook = document.getElementById("hook");
  hook.querySelector(".l1").textContent = (S.hook && S.hook.line1) || "";
  hook.querySelector(".l2").textContent = (S.hook && S.hook.line2) || "";

  // 하단 자막 — 브라우저 자동 줄바꿈에 맡기지 않고 **어절(띄어쓰기) 사이에서만** 직접 나눈다.
  //   한 줄 ≤ LINE_EM(전각 1 · 반각 0.55), 한 화면 ≤ 2줄. 문장이 길면 화면 여러 장으로 나눠 글자 수 비율로 시간 배분.
  //   키워드·연속 영문 대문자(GROUP BY, IS NOT NULL)·「TRUNCATE 는」 같은 영문+조사는 한 덩어리로 묶어 쪼개지 않는다.
  var LINE_EM = 15.5, NBSP = " ";
  var esc = function (s) { return String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); };
  var wch = function (ch) { return /[ᄀ-ᇿ　-鿿가-힯＀-￯]/.test(ch) ? 1 : (ch === " " || ch === NBSP ? 0.3 : 0.55); };
  var wid = function (s) { var w = 0; for (var k = 0; k < s.length; k++) w += wch(s[k]); return w; };
  var glue = function (text, kws) {
    var t = String(text).replace(/\s+/g, " ").trim();
    (kws || []).forEach(function (k) { if (k && k.indexOf(" ") >= 0) t = t.split(k).join(k.replace(/ /g, NBSP)); });
    t = t.replace(/\b[A-Z][A-Z0-9_()%*.,]*(?: [A-Z][A-Z0-9_()%*]*)+/g, function (m) { return m.replace(/ /g, NBSP); });
    t = t.replace(/([A-Za-z0-9)%]) (은|는|이|가|을|를|의|에|와|과|로|으로|도|만|에서|까지|부터|보다|처럼|이나|나)(?=[ ,.?!]|$)/g, "$1" + NBSP + "$2");
    return t;
  };
  var balance2 = function (words) {           // 두 줄로 나눌 때 긴 줄이 가장 짧아지는 곳에서
    var best = 1, bw = 1e9;
    for (var k = 1; k < words.length; k++) {
      var m = Math.max(wid(words.slice(0, k).join(" ")), wid(words.slice(k).join(" ")));
      if (/^[가-힯]$/.test(words[k - 1])) m += 4;         // 「그 / 쿼리」처럼 한 글자 낱말을 줄 끝에 홀로 두지 않는다
      if (/[,.?!]$/.test(words[k - 1])) m -= 1.5;                  // 쉼표·마침표 뒤에서 끊으면 읽기 쉽다
      if (m < bw) { bw = m; best = k; }
    }
    return [words.slice(0, best).join(" "), words.slice(best).join(" ")];
  };
  var screens = function (text) {             // → [[줄, 줄?], …]
    var words = text.split(" ").filter(Boolean), total = wid(text);
    if (!words.length) return [[""]];
    if (total <= LINE_EM || words.length === 1) return [[text]];
    if (total <= LINE_EM * 2) return [balance2(words)];
    var n = Math.ceil(total / (LINE_EM * 1.8)), out = [], cur = [], target = total / n;
    words.forEach(function (w, k) {
      cur.push(w);
      var cw = wid(cur.join(" ")), left = words.length - k - 1;
      var soft = /[,.?!…]$/.test(w) && cw >= target * 0.6;          // 쉼표·마침표 뒤에서 끊으면 자연스럽다
      if (left && out.length < n - 1 && (cw >= target || soft)) { out.push(cur); cur = []; }
    });
    if (cur.length) out.push(cur);
    return out.map(function (ws) { var s = ws.join(" "); return wid(s) <= LINE_EM || ws.length === 1 ? [s] : balance2(ws); });
  };
  var paint = function (line, kws) {
    var h = esc(line);
    (kws || []).forEach(function (k) {
      if (!k) return;
      var e = esc(k.replace(/ /g, NBSP));
      h = h.split(e).join('<b class="kw">' + e + "</b>");
      if (e !== esc(k)) h = h.split(esc(k)).join('<b class="kw">' + esc(k) + "</b>");
    });
    return '<div class="ln">' + h + "</div>";
  };
  var caps = document.getElementById("captions");
  S.cues.forEach(function (c) {
    var parts = screens(glue(c.text, c.keywords));
    var weights = parts.map(function (p) { return Math.max(1, wid(p.join(" "))); });
    var sum = weights.reduce(function (a, b) { return a + b; }, 0), t = c.start, span = Math.max(0.2, c.end - c.start);
    c._els = parts.map(function (p, k) {
      var el = document.createElement("div");
      el.className = "cap";
      el.innerHTML = "<span>" + p.map(function (ln) { return paint(ln, c.keywords); }).join("") + "</span>";
      caps.appendChild(el);
      var at0 = t;
      t += span * weights[k] / sum;
      return { el: el, start: at0 };
    });
  });

  // 칸을 넘으면 글자 크기를 줄인다(줄은 이미 어절 사이에서 나뉘어 있다)
  var fit = function (el, box, maxW, maxH, minPx) {
    var cs = parseFloat(getComputedStyle(el).fontSize) || 54;
    var guard = 0;
    while ((el.scrollWidth > maxW + 1 || (maxH && box.scrollHeight > maxH + 1)) && cs > minPx && guard++ < 40) {
      cs -= 2;
      el.style.fontSize = cs + "px";
    }
    return el.scrollWidth <= maxW + 1 && (!maxH || box.scrollHeight <= maxH + 1);
  };
  window.__overflow = [];
  var fitAll = function () {
    var cw = caps.clientWidth, ch = caps.clientHeight;
    S.cues.forEach(function (c) {
      (c._els || []).forEach(function (x) {
        var sp = x.el.firstChild;
        if (!fit(sp, sp, cw, ch, 38)) {        // 띄어쓰기 없는 아주 긴 덩어리 — 마지막 수단으로만 글자 단위 줄바꿈
          Array.prototype.forEach.call(sp.querySelectorAll(".ln"), function (l) { l.style.whiteSpace = "normal"; l.style.overflowWrap = "anywhere"; });
          window.__overflow.push("[자막] 칸을 넘음 — 대본 편집에서 문장을 줄이거나 띄어 써 주세요: " + sp.textContent.slice(0, 30));
        }
      });
    });
    var hw = hook.clientWidth - 120;
    [hook.querySelector(".l1"), hook.querySelector(".l2")].forEach(function (el, k) {
      if (!el.textContent) return;
      el.classList.add("nw");
      if (!fit(el, el, hw, 0, k ? 34 : 50)) {          // 한 줄로 안 되면 어절 사이 두 줄(keep-all)
        el.classList.remove("nw");
      }
    });
    if (hook.scrollHeight > hook.clientHeight + 1) window.__overflow.push("[자막] 후크가 칸을 넘음 — 대본 편집에서 후크를 줄여 주세요: " + hook.textContent.slice(0, 30));
  };

  window.__finish = function () {
    try {
      // 후크는 첫 프레임부터 보인다(스크롤 3초 안에 멈추게 · 첫 프레임 = 미리보기 장면) — 살짝 튀는 것만
      TL.fromTo(hook, { scale: 1.08 }, { scale: 1, duration: 0.35, ease: "back.out(2)" }, 0);
      var flat = [];
      S.cues.forEach(function (c) { (c._els || []).forEach(function (x) { flat.push(x); }); });
      flat.forEach(function (x, i) {
        var next = flat[i + 1];
        var off = next ? next.start : S.duration;
        TL.fromTo(x.el, { opacity: 0, y: 18, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.16, ease: "back.out(1.8)" }, x.start);
        TL.to(x.el, { opacity: 0, duration: 0.08, ease: "none" }, Math.max(x.start + 0.2, off - 0.06));
      });
      TL.set({}, {}, S.duration);          // 타임라인 길이 = 음성 길이
    } catch (e) { window.__errors.push("finish: " + (e && e.stack || e)); }
    var imgs = Array.prototype.slice.call(document.images);
    Promise.all([document.fonts.ready].concat(imgs.map(function (im) {
      return im.decode ? im.decode().catch(function () { window.__errors.push("그림을 못 읽음: " + im.getAttribute("src")); }) : null;
    }))).then(function () {
      try { fitAll(); } catch (e) { window.__errors.push("fit: " + (e && e.stack || e)); }
      TL.seek(0, false); window.__ready = true;
    });
  };

  window.__seek = function (t) {
    TL.seek(t, false);
    if (document.getAnimations) document.getAnimations().forEach(function (a) { a.pause(); a.currentTime = t * 1000; });
  };
  // 브라우저에서 그냥 열었을 때(미리보기) — 실시간 재생 + 음성
  window.__play = function () {
    var a = document.getElementById("__audio");
    TL.seek(0).play();
    if (a) { a.currentTime = 0; a.play(); }
  };
})();
