(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"})[ch]);

  async function api(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : (data.detail?.message || "Request failed.");
      throw new Error(detail);
    }
    return data;
  }

  function formValues() {
    return {
      support_key: $("supportKey").value.trim(),
      email: $("customerEmail").value.trim(),
      payment_identifier: $("paymentIdentifier").value.trim(),
      operator_note: $("operatorNote").value.trim(),
    };
  }

  function productName(area) {
    if (area === "topic_ideas") return "Topic Ideas";
    if (area === "chapter_strengthener") return "Chapter Strengthener";
    return "Thesis Workspace";
  }

  function renderPurchases(purchases) {
    const results = $("results");
    if (!purchases.length) {
      results.innerHTML = '<div class="panel empty">No payment records matched that email and identifier.</div>';
      return;
    }
    results.innerHTML = purchases.map(p => `
      <article class="purchase-card">
        <div class="purchase-heading">
          <div>
            <p class="eyebrow">${esc(productName(p.product_area))}</p>
            <h2>${esc(p.plan_key || "Payment record")}</h2>
          </div>
          <span class="status-badge status-${esc(String(p.status || "pending").toLowerCase())}">${esc(p.status || "pending")}</span>
        </div>
        <dl>
          <div><dt>Purchase ID</dt><dd>${esc(p.purchase_id)}</dd></div>
          <div><dt>Payment reference</dt><dd>${esc(p.provider_reference || "Not recorded")}</dd></div>
          <div><dt>Stripe session</dt><dd>${esc(p.checkout_session_id || "Not applicable")}</dd></div>
          <div><dt>Provider</dt><dd>${esc(p.payment_provider)}</dd></div>
          <div><dt>Amount</dt><dd>${esc(p.currency)} ${Number(p.amount || 0).toFixed(2)}</dd></div>
          <div><dt>Project / access ID</dt><dd>${esc(p.project_id || "")}</dd></div>
          <div><dt>Chapter</dt><dd>${esc(p.chapter_title || p.chapter_number || "Not applicable")}</dd></div>
          <div><dt>Paid</dt><dd>${esc(p.paid_at || "Not yet verified")}</dd></div>
          <div><dt>Expires</dt><dd>${esc(p.expires_at || "")}</dd></div>
        </dl>
        <button class="create-link" type="button" data-purchase-id="${esc(p.purchase_id)}">Create one-time recovery link</button>
      </article>
    `).join("");

    results.querySelectorAll(".create-link").forEach(button => {
      button.addEventListener("click", () => createLink(button.dataset.purchaseId, button));
    });
  }

  async function search() {
    const button = $("searchPayments");
    const values = formValues();
    if (!values.support_key || !values.email.includes("@")) {
      $("status").textContent = "Enter the support key and the customer’s exact payment email.";
      return;
    }
    button.disabled = true;
    $("status").textContent = "Searching the persistent payment database...";
    $("linkPanel").hidden = true;
    try {
      const data = await api("/api/admin/payment-recovery/search", values);
      renderPurchases(data.purchases || []);
      $("status").textContent = `${data.count || 0} payment record(s) found.`;
    } catch (error) {
      $("results").innerHTML = "";
      $("status").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  async function createLink(purchaseId, button) {
    const values = formValues();
    button.disabled = true;
    $("status").textContent = "Verifying the payment and creating a secure recovery link...";
    try {
      const data = await api("/api/admin/payment-recovery/create-link", {
        support_key: values.support_key,
        email: values.email,
        purchase_id: purchaseId,
        operator_note: values.operator_note,
      });
      $("recoveryUrl").value = data.recovery_url;
      $("linkPanel").hidden = false;
      $("status").textContent = "Recovery link created. It expires in 60 minutes and can be used once.";
      $("linkPanel").scrollIntoView({behavior: "smooth", block: "start"});
    } catch (error) {
      $("status").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  $("searchPayments").addEventListener("click", search);
  $("copyRecoveryUrl").addEventListener("click", async () => {
    const value = $("recoveryUrl").value;
    try {
      await navigator.clipboard.writeText(value);
      $("status").textContent = "Recovery link copied.";
    } catch (_) {
      $("recoveryUrl").select();
      document.execCommand("copy");
      $("status").textContent = "Recovery link copied.";
    }
  });
})();
