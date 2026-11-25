/**
 * Runs on Google's servers once a minute. The computer can be closed, asleep, or off.
 * Each send time still produces one email. Opening the computer does not send another.
 */

var USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

var SOURCES = [
  { name: "Reuters", url: "https://news.google.com/rss/search?q=when:2d+site:reuters.com+(inflation+OR+%22interest+rate%22+OR+%22Federal+Reserve%22+OR+ECB+OR+recession+OR+tariff+OR+%22oil%22+OR+GDP+OR+%22central+bank%22)&hl=en-US&gl=US&ceid=US:en", rank: 0 },
  { name: "AP News", url: "https://news.google.com/rss/search?q=when:2d+site:apnews.com+(inflation+OR+%22interest+rate%22+OR+%22Federal+Reserve%22+OR+economy+OR+tariff+OR+jobs+OR+GDP)&hl=en-US&gl=US&ceid=US:en", rank: 1 },
  { name: "Financial Times", url: "https://www.ft.com/world/economy?format=rss", rank: 2 },
  { name: "Wall Street Journal", url: "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", rank: 3 },
  { name: "The Economist", url: "https://www.economist.com/finance-and-economics/rss.xml", rank: 4 },
  { name: "BBC Business", url: "https://feeds.bbci.co.uk/news/business/rss.xml", rank: 5 },
  { name: "CNBC", url: "https://www.cnbc.com/id/100003114/device/rss/rss.html", rank: 6 },
  { name: "NPR Economy", url: "https://feeds.npr.org/1006/rss.xml", rank: 7 }
];

var IMPACT_TERMS = [
  ["\\bfederal reserve\\b|\\bfomc\\b|\\brate cut\\b|\\brate hike\\b|\\binterest rates?\\b|\\becb\\b|\\beuropean central bank\\b|\\bbank of england\\b|\\bbank of japan\\b|\\bboj\\b|\\bpboc\\b|\\bcentral bank\\b", 100],
  ["\\binflation\\b|\\bcpi\\b|\\bpce\\b|\\bconsumer prices?\\b|\\bjobs report\\b|\\bnonfarm\\b|\\bpayrolls?\\b|\\bunemployment\\b|\\brecession\\b|\\bgdp\\b", 90],
  ["\\bopec\\b|\\bcrude\\b|\\bbrent\\b|\\boil price\\b|\\bsanctions?\\b|\\binvasion\\b|\\bwar\\b|\\btariffs?\\b|\\btrade war\\b|\\bdefault\\b|\\bbank failure\\b|\\bcredit crisis\\b|\\bstimulus\\b", 80],
  ["\\byields?\\b|\\btreasury\\b|\\bdollar\\b|\\byen\\b|\\beuro\\b|\\byuan\\b|\\bs&p\\b|\\bnasdaq\\b|\\bstock market\\b|\\bwall street\\b|\\bsell-?off\\b|\\brally\\b", 55],
  ["\\bpmi\\b|\\bretail sales\\b|\\bmanufacturing\\b|\\bhousing\\b|\\bconsumer confidence\\b|\\bearnings\\b|\\bguidance\\b", 30],
  ["\\beconomy\\b|\\beconomic\\b|\\bmarkets?\\b|\\binvestors?\\b|\\bstocks?\\b|\\bshares\\b|\\btrade\\b", 15]
];

var NOISE_RE = /\b(celebrity|wedding|recipe|football|soccer|nba|nfl|oscar|box office|obituary|royals?)\b/i;
var SOFT_RE = /\b(meet the|identity crisis|commentary|opinion|explainer|newsletter|scandal|comeback|what to know)\b/i;
var STOP_WORDS = {
  the: 1, a: 1, an: 1, of: 1, to: 1, and: 1, in: 1, on: 1, for: 1, as: 1, at: 1, by: 1,
  from: 1, with: 1, after: 1, over: 1, its: 1, into: 1, that: 1, this: 1, are: 1, was: 1
};

function settings_() {
  if (typeof CONFIG === "undefined") {
    throw new Error("Missing settings.");
  }
  return CONFIG;
}

function sendDailyNews() {
  try {
    maybeSend_();
  } catch (err) {
    console.error(err);
  }
}

function maybeSend_() {
  var cfg = settings_();
  if (!cfg.enabled) return;

  var tz = cfg.timeZone || Session.getScriptTimeZone();
  var now = new Date();
  var day = Utilities.formatDate(now, tz, "yyyy-MM-dd");
  var hhmm = Utilities.formatDate(now, tz, "HH:mm");
  var slot = day + "T" + cfg.sendTime;
  if (cfg.notBefore && slot < cfg.notBefore) return;
  if (hhmm < cfg.sendTime) return;
  if (minutesAfter_(hhmm, cfg.sendTime) > 180) return;

  var recipients = [];
  (cfg.recipients || []).forEach(function (email) {
    if (email && String(email).trim()) recipients.push(String(email).trim());
  });
  if (!recipients.length) return;

  var props = PropertiesService.getScriptProperties();
  if (props.getProperty("lastSlot") === slot) return;

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return;
  try {
    if (props.getProperty("lastSlot") === slot) return;
    var headlines = fetchHeadlines_(5);
    if (!headlines.length) throw new Error("No headlines available.");
    sendEmail_(cfg, recipients, headlines, now, tz);
    props.setProperty("lastSlot", slot);
    props.deleteProperty("lastError");
  } catch (err) {
    props.setProperty("lastError", String(err));
    console.error(err);
  } finally {
    lock.releaseLock();
  }
}

function minutesAfter_(hhmm, sendTime) {
  function mins(value) {
    var parts = String(value || "00:00").split(":");
    return Number(parts[0]) * 60 + Number(parts[1]);
  }
  return mins(hhmm) - mins(sendTime);
}

function installTrigger_() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (trigger.getHandlerFunction() === "sendDailyNews") {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  try {
    ScriptApp.newTrigger("sendDailyNews").timeBased().everyMinutes(1).create();
  } catch (err) {
    ScriptApp.newTrigger("sendDailyNews").timeBased().everyMinutes(5).create();
  }
}

// Public name so the editor Run menu can start the schedule on the latest code.
// A trigger created from the published web page stays stuck on that old copy.
function installSchedule() {
  installTrigger_();
}

function doGet() {
  var page = "<html><head><meta charset=\"utf-8\"></head><body style=\"font-family:Segoe UI,sans-serif;margin:48px auto;max-width:36rem;line-height:1.5;\">" +
    "<p>Gmail is approved. Close this tab, go back to Daily News Brief, and click <strong>I've finished the Google page</strong>.</p>" +
    "<p>The daily email is sent from the latest saved schedule, including when the computer is closed.</p></body></html>";
  return HtmlService.createHtmlOutput(page);
}

function fetchHeadlines_(count) {
  var collected = [];
  var seen = {};
  SOURCES.forEach(function (source) {
    var xml = "";
    try {
      xml = fetchFeed_(source.url);
    } catch (err) {
      return;
    }
    extractBlocks_(xml).slice(0, 12).forEach(function (block) {
      var title = cleanText_(tagText_(block, "title"), 160);
      title = title.replace(/\s+-\s+(Reuters|AP News|AP|BBC|CNBC|FT|WSJ)$/i, "").trim();
      if (!title) return;
      var key = title.toLowerCase();
      if (seen[key]) return;
      seen[key] = 1;
      var summary = itemSummary_(block);
      var blob = title + " " + summary;
      if (NOISE_RE.test(blob)) return;
      collected.push({
        title: title,
        summary: summary,
        link: itemLink_(block),
        source: source.name,
        score: impactScore_(blob),
        rank: source.rank
      });
    });
  });

  collected.sort(function (a, b) {
    if (b.score !== a.score) return b.score - a.score;
    return a.rank - b.rank;
  });

  var ranked = [];
  collected.forEach(function (item) {
    if (ranked.length >= count) return;
    if (item.score <= 0 && ranked.length >= count) return;
    if (tooSimilar_(item.title, ranked)) return;
    ranked.push({
      title: item.title,
      summary: item.summary,
      link: item.link,
      source: item.source
    });
  });
  return ranked;
}

function fetchFeed_(url) {
  var response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    followRedirects: true,
    headers: {
      "User-Agent": USER_AGENT,
      "Accept": "application/rss+xml, application/xml, text/xml, */*"
    }
  });
  var code = response.getResponseCode();
  if (code >= 400) throw new Error("Feed status " + code);
  var text = response.getContentText() || "";
  if (text.indexOf("<item") === -1 && text.indexOf("<entry") === -1) {
    throw new Error("No stories in feed");
  }
  return text;
}

function extractBlocks_(xml) {
  var blocks = [];
  var match;
  var pattern = /<(item|entry)\b[\s\S]*?<\/\1>/gi;
  while ((match = pattern.exec(xml))) {
    blocks.push(match[0]);
  }
  return blocks;
}

function tagText_(block, tag) {
  var cdata = new RegExp("<" + tag + "[^>]*>\\s*<!\\[CDATA\\[([\\s\\S]*?)\\]\\]>\\s*</" + tag + ">", "i");
  var plain = new RegExp("<" + tag + "[^>]*>([\\s\\S]*?)</" + tag + ">", "i");
  var found = block.match(cdata) || block.match(plain);
  return found ? found[1] : "";
}

function itemLink_(block) {
  var atom = block.match(/<link\b[^>]*href=["']([^"']+)["']/i);
  if (atom) return decode_(atom[1]);
  var rss = block.match(/<link[^>]*>\s*([^<\s][^<]*?)\s*<\/link>/i);
  return rss ? decode_(rss[1]).trim() : "";
}

function itemSummary_(block) {
  var raw = tagText_(block, "description") || tagText_(block, "summary") || tagText_(block, "content");
  var cleaned = cleanText_(raw, 320);
  return cleaned || "Open the article for the full story.";
}

function decode_(value) {
  return String(value || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#(\d+);/g, function (_, num) { return String.fromCharCode(Number(num)); });
}

function cleanText_(value, limit) {
  var text = decode_(value).replace(/\s+/g, " ").trim();
  if (text.length > limit) text = text.slice(0, limit - 1).trim() + "…";
  return text;
}

function impactScore_(text) {
  var macro = 0;
  var extra = 0;
  IMPACT_TERMS.forEach(function (pair) {
    if (new RegExp(pair[0], "i").test(text)) {
      if (pair[1] >= 55) macro += pair[1];
      else extra += pair[1];
    }
  });
  var score = macro + Math.min(extra, 20);
  if (SOFT_RE.test(text)) score -= 60;
  return score;
}

function tokens_(title) {
  var words = String(title || "").toLowerCase().match(/[a-z0-9]+/g) || [];
  var out = [];
  words.forEach(function (word) {
    if (!STOP_WORDS[word] && word.length > 2) out.push(word);
  });
  return out;
}

function tooSimilar_(title, chosen) {
  var current = tokens_(title);
  if (!current.length) return false;
  for (var i = 0; i < chosen.length; i++) {
    var other = tokens_(chosen[i].title);
    if (!other.length) continue;
    var otherMap = {};
    other.forEach(function (word) { otherMap[word] = 1; });
    var overlap = 0;
    current.forEach(function (word) { if (otherMap[word]) overlap++; });
    var denom = Math.min(current.length, other.length);
    if (denom && overlap / denom >= 0.6) return true;
  }
  return false;
}

function sendEmail_(cfg, recipients, headlines, now, tz) {
  var title = String(cfg.emailTitle || "Daily News Brief").trim() || "Daily News Brief";
  var fromName = String(cfg.fromName || "Daily News Brief").trim() || "Daily News Brief";
  var subject = title + " — " + Utilities.formatDate(now, tz, "MMM dd, yyyy");
  var message = {
    to: recipients.join(","),
    subject: subject,
    body: buildText_(headlines, now, tz, title),
    htmlBody: buildHtml_(headlines, now, tz, title),
    name: fromName
  };
  if (cfg.fromEmail) message.replyTo = String(cfg.fromEmail).trim();
  MailApp.sendEmail(message);
}

function buildHtml_(headlines, now, tz, title) {
  var when = Utilities.formatDate(now, tz, "EEEE, MMMM dd, yyyy");
  var items = headlines.map(function (story, index) {
    var link = story.link || "#";
    return "<tr><td style=\"padding:0 0 28px 0;border-bottom:1px solid #e6e2da;\">" +
      "<p style=\"margin:0 0 6px 0;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#6b655c;\">" +
      (index + 1) + ". " + esc_(story.source || "News") + "</p>" +
      "<h2 style=\"margin:0 0 10px 0;font-size:20px;line-height:1.35;color:#1c1915;\">" +
      "<a href=\"" + esc_(link) + "\" style=\"color:#1c1915;text-decoration:none;\">" + esc_(story.title) + "</a></h2>" +
      "<p style=\"margin:0 0 12px 0;font-size:15px;line-height:1.55;color:#4a453c;\">" + esc_(story.summary || "") + "</p>" +
      "<a href=\"" + esc_(link) + "\" style=\"font-size:14px;color:#0b5fff;text-decoration:none;font-weight:600;\">Read more →</a>" +
      "</td></tr>";
  }).join("");

  return "<!DOCTYPE html><html><body style=\"margin:0;padding:0;background:#f3efe7;font-family:Georgia,'Times New Roman',serif;\">" +
    "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f3efe7;padding:32px 16px;\"><tr><td align=\"center\">" +
    "<table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"max-width:600px;background:#fffdf8;border:1px solid #ddd6c8;padding:36px 32px;\"><tr><td>" +
    "<p style=\"margin:0 0 4px 0;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:#8a8276;\">" + esc_(title) + "</p>" +
    "<h1 style=\"margin:0 0 8px 0;font-size:28px;color:#1c1915;\">Market-moving headlines</h1>" +
    "<p style=\"margin:0 0 28px 0;font-size:14px;color:#6b655c;\">" + esc_(when) + "</p>" +
    "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\">" + items + "</table>" +
    "<p style=\"margin:28px 0 0 0;font-size:12px;color:#8a8276;line-height:1.5;\">Ranked by likely market impact, largest first. Sources include Reuters, AP, the Financial Times, The Wall Street Journal, The Economist, and BBC.</p>" +
    "</td></tr></table></td></tr></table></body></html>";
}

function buildText_(headlines, now, tz, title) {
  var when = Utilities.formatDate(now, tz, "EEEE, MMMM dd, yyyy");
  var lines = [title + " — " + when, "", "Market-moving headlines, largest impact first", ""];
  headlines.forEach(function (story, index) {
    lines.push((index + 1) + ". [" + (story.source || "News") + "] " + story.title);
    lines.push(story.summary || "");
    if (story.link) lines.push(story.link);
    lines.push("");
  });
  lines.push("Sources: Reuters, AP, Financial Times, Wall Street Journal, The Economist, BBC");
  return lines.join("\n");
}

function esc_(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
