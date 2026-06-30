(() => {
  "use strict";
  const message = document.getElementById("recoveryMessage");
  const continueButton = document.getElementById("continueButton");

  function storeCredential(data) {
    const value = {
      purchase_id: data.purchase_id,
      access_token: data.access_token,
      provider: data.provider || "",
      saved_at: new Date().toISOString(),
    };
    if (data.product_area === "topic_ideas") {
      const topicValue = {...value, access_id: data.project_id || ""};
      sessionStorage.setItem("projectready-topic-ideas-access-v1", JSON.stringify(topicValue));
      localStorage.setItem("projectready-topic-ideas-access-v1", JSON.stringify(topicValue));
    } else {
      const projectId = String(data.project_id || "");
      const chapterNumber = Number(data.chapter_number || 0);
      localStorage.setItem(`projectready-entitlement:${projectId}:chapter-${chapterNumber}`, JSON.stringify(value));
      localStorage.setItem(`projectready-entitlement:purchase:${data.purchase_id}`, JSON.stringify(value));
    }
  }

  function safeDestination(data) {
    let path = String(data.return_path || "").trim();
    if (!path.startsWith("/") || path.startsWith("//") || path.startsWith("/api/") || path.startsWith("/payment/")) {
      path = data.product_area === "topic_ideas" ? "/topic-ideas" : "/workspace";
    }
    const url = new URL(path, window.location.origin);
    url.searchParams.set("access_restored", "1");
    if (data.project_id && data.product_area !== "topic_ideas") url.searchParams.set("project_id", data.project_id);
    if (data.chapter_number && data.product_area !== "topic_ideas") url.searchParams.set("chapter", data.chapter_number);
    return url.pathname + url.search;
  }

  async function restore() {
    const handoff = new URLSearchParams(window.location.search).get("handoff") || "";
    if (!handoff) {
      message.textContent = "This recovery link is incomplete. Contact ProjectReady AI support for a new link.";
      return;
    }
    try {
      const response = await fetch("/api/payments/redeem-recovery", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({handoff}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "The recovery link could not be redeemed.");
      storeCredential(data);
      const destination = safeDestination(data);
      message.textContent = "Paid access has been restored on this device. You may continue to the service you purchased.";
      continueButton.hidden = false;
      continueButton.onclick = () => window.location.assign(destination);
      window.setTimeout(() => window.location.assign(destination), 1800);
    } catch (error) {
      message.textContent = error.message || "The recovery link is invalid, expired or has already been used.";
    }
  }
  restore();
})();
