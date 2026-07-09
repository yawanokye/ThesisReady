/* ProjectReady AI registration and chapter checkout UI. */
(() => {
  "use strict";

  const COUNTRIES = [["AF", "Afghanistan"], ["AL", "Albania"], ["DZ", "Algeria"], ["AS", "American Samoa"], ["AD", "Andorra"], ["AO", "Angola"], ["AI", "Anguilla"], ["AQ", "Antarctica"], ["AG", "Antigua and Barbuda"], ["AR", "Argentina"], ["AM", "Armenia"], ["AW", "Aruba"], ["AU", "Australia"], ["AT", "Austria"], ["AZ", "Azerbaijan"], ["BS", "Bahamas"], ["BH", "Bahrain"], ["BD", "Bangladesh"], ["BB", "Barbados"], ["BY", "Belarus"], ["BE", "Belgium"], ["BZ", "Belize"], ["BJ", "Benin"], ["BM", "Bermuda"], ["BT", "Bhutan"], ["BO", "Bolivia, Plurinational State of"], ["BQ", "Bonaire, Sint Eustatius and Saba"], ["BA", "Bosnia and Herzegovina"], ["BW", "Botswana"], ["BV", "Bouvet Island"], ["BR", "Brazil"], ["IO", "British Indian Ocean Territory"], ["BN", "Brunei Darussalam"], ["BG", "Bulgaria"], ["BF", "Burkina Faso"], ["BI", "Burundi"], ["CV", "Cabo Verde"], ["KH", "Cambodia"], ["CM", "Cameroon"], ["CA", "Canada"], ["KY", "Cayman Islands"], ["CF", "Central African Republic"], ["TD", "Chad"], ["CL", "Chile"], ["CN", "China"], ["CX", "Christmas Island"], ["CC", "Cocos (Keeling) Islands"], ["CO", "Colombia"], ["KM", "Comoros"], ["CG", "Congo"], ["CD", "Congo, The Democratic Republic of the"], ["CK", "Cook Islands"], ["CR", "Costa Rica"], ["HR", "Croatia"], ["CU", "Cuba"], ["CW", "Curaçao"], ["CY", "Cyprus"], ["CZ", "Czechia"], ["CI", "Côte d'Ivoire"], ["DK", "Denmark"], ["DJ", "Djibouti"], ["DM", "Dominica"], ["DO", "Dominican Republic"], ["EC", "Ecuador"], ["EG", "Egypt"], ["SV", "El Salvador"], ["GQ", "Equatorial Guinea"], ["ER", "Eritrea"], ["EE", "Estonia"], ["SZ", "Eswatini"], ["ET", "Ethiopia"], ["FK", "Falkland Islands (Malvinas)"], ["FO", "Faroe Islands"], ["FJ", "Fiji"], ["FI", "Finland"], ["FR", "France"], ["GF", "French Guiana"], ["PF", "French Polynesia"], ["TF", "French Southern Territories"], ["GA", "Gabon"], ["GM", "Gambia"], ["GE", "Georgia"], ["DE", "Germany"], ["GH", "Ghana"], ["GI", "Gibraltar"], ["GR", "Greece"], ["GL", "Greenland"], ["GD", "Grenada"], ["GP", "Guadeloupe"], ["GU", "Guam"], ["GT", "Guatemala"], ["GG", "Guernsey"], ["GN", "Guinea"], ["GW", "Guinea-Bissau"], ["GY", "Guyana"], ["HT", "Haiti"], ["HM", "Heard Island and McDonald Islands"], ["VA", "Holy See (Vatican City State)"], ["HN", "Honduras"], ["HK", "Hong Kong"], ["HU", "Hungary"], ["IS", "Iceland"], ["IN", "India"], ["ID", "Indonesia"], ["IR", "Iran, Islamic Republic of"], ["IQ", "Iraq"], ["IE", "Ireland"], ["IM", "Isle of Man"], ["IL", "Israel"], ["IT", "Italy"], ["JM", "Jamaica"], ["JP", "Japan"], ["JE", "Jersey"], ["JO", "Jordan"], ["KZ", "Kazakhstan"], ["KE", "Kenya"], ["KI", "Kiribati"], ["KP", "Korea, Democratic People's Republic of"], ["KR", "Korea, Republic of"], ["KW", "Kuwait"], ["KG", "Kyrgyzstan"], ["LA", "Lao People's Democratic Republic"], ["LV", "Latvia"], ["LB", "Lebanon"], ["LS", "Lesotho"], ["LR", "Liberia"], ["LY", "Libya"], ["LI", "Liechtenstein"], ["LT", "Lithuania"], ["LU", "Luxembourg"], ["MO", "Macao"], ["MG", "Madagascar"], ["MW", "Malawi"], ["MY", "Malaysia"], ["MV", "Maldives"], ["ML", "Mali"], ["MT", "Malta"], ["MH", "Marshall Islands"], ["MQ", "Martinique"], ["MR", "Mauritania"], ["MU", "Mauritius"], ["YT", "Mayotte"], ["MX", "Mexico"], ["FM", "Micronesia, Federated States of"], ["MD", "Moldova, Republic of"], ["MC", "Monaco"], ["MN", "Mongolia"], ["ME", "Montenegro"], ["MS", "Montserrat"], ["MA", "Morocco"], ["MZ", "Mozambique"], ["MM", "Myanmar"], ["NA", "Namibia"], ["NR", "Nauru"], ["NP", "Nepal"], ["NL", "Netherlands"], ["NC", "New Caledonia"], ["NZ", "New Zealand"], ["NI", "Nicaragua"], ["NE", "Niger"], ["NG", "Nigeria"], ["NU", "Niue"], ["NF", "Norfolk Island"], ["MK", "North Macedonia"], ["MP", "Northern Mariana Islands"], ["NO", "Norway"], ["OM", "Oman"], ["PK", "Pakistan"], ["PW", "Palau"], ["PS", "Palestine, State of"], ["PA", "Panama"], ["PG", "Papua New Guinea"], ["PY", "Paraguay"], ["PE", "Peru"], ["PH", "Philippines"], ["PN", "Pitcairn"], ["PL", "Poland"], ["PT", "Portugal"], ["PR", "Puerto Rico"], ["QA", "Qatar"], ["RO", "Romania"], ["RU", "Russian Federation"], ["RW", "Rwanda"], ["RE", "Réunion"], ["BL", "Saint Barthélemy"], ["SH", "Saint Helena, Ascension and Tristan da Cunha"], ["KN", "Saint Kitts and Nevis"], ["LC", "Saint Lucia"], ["MF", "Saint Martin (French part)"], ["PM", "Saint Pierre and Miquelon"], ["VC", "Saint Vincent and the Grenadines"], ["WS", "Samoa"], ["SM", "San Marino"], ["ST", "Sao Tome and Principe"], ["SA", "Saudi Arabia"], ["SN", "Senegal"], ["RS", "Serbia"], ["SC", "Seychelles"], ["SL", "Sierra Leone"], ["SG", "Singapore"], ["SX", "Sint Maarten (Dutch part)"], ["SK", "Slovakia"], ["SI", "Slovenia"], ["SB", "Solomon Islands"], ["SO", "Somalia"], ["ZA", "South Africa"], ["GS", "South Georgia and the South Sandwich Islands"], ["SS", "South Sudan"], ["ES", "Spain"], ["LK", "Sri Lanka"], ["SD", "Sudan"], ["SR", "Suriname"], ["SJ", "Svalbard and Jan Mayen"], ["SE", "Sweden"], ["CH", "Switzerland"], ["SY", "Syrian Arab Republic"], ["TW", "Taiwan, Province of China"], ["TJ", "Tajikistan"], ["TZ", "Tanzania, United Republic of"], ["TH", "Thailand"], ["TL", "Timor-Leste"], ["TG", "Togo"], ["TK", "Tokelau"], ["TO", "Tonga"], ["TT", "Trinidad and Tobago"], ["TN", "Tunisia"], ["TM", "Turkmenistan"], ["TC", "Turks and Caicos Islands"], ["TV", "Tuvalu"], ["TR", "Türkiye"], ["UG", "Uganda"], ["UA", "Ukraine"], ["AE", "United Arab Emirates"], ["GB", "United Kingdom"], ["US", "United States"], ["UM", "United States Minor Outlying Islands"], ["UY", "Uruguay"], ["UZ", "Uzbekistan"], ["VU", "Vanuatu"], ["VE", "Venezuela, Bolivarian Republic of"], ["VN", "Viet Nam"], ["VG", "Virgin Islands, British"], ["VI", "Virgin Islands, U.S."], ["WF", "Wallis and Futuna"], ["EH", "Western Sahara"], ["YE", "Yemen"], ["ZM", "Zambia"], ["ZW", "Zimbabwe"], ["AX", "Åland Islands"]];
  const AFRICAN_COUNTRIES = new Set([
    "DZ", "AO", "BJ", "BW", "BF", "BI", "CV", "CM", "CF", "TD",
    "KM", "CG", "CD", "CI", "DJ", "EG", "GQ", "ER", "SZ", "ET",
    "GA", "GM", "GH", "GN", "GW", "KE", "LS", "LR", "LY", "MG",
    "MW", "ML", "MR", "MU", "MA", "MZ", "NA", "NE", "NG", "RW",
    "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD", "TZ", "TG",
    "TN", "UG", "ZM", "ZW"
  ]);
  const STORAGE_PREFIX = "projectready-entitlement:";
  const REGISTRATION_PROFILE_KEY = "projectready_registration_profile";

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[ch]);

  function entitlementKey(projectId, chapterNumber) {
    return `${STORAGE_PREFIX}${projectId}:chapter-${chapterNumber}`;
  }

  function readRegistrationProfile() {
    try {
      const profile = JSON.parse(localStorage.getItem(REGISTRATION_PROFILE_KEY) || "null");
      return profile && typeof profile === "object" ? profile : null;
    } catch (_) {
      return null;
    }
  }

  function hasRegistrationProfile() {
    const profile = readRegistrationProfile();
    return Boolean(profile?.email && profile?.full_name);
  }

  function registrationUrl(options = {}) {
    const returnUrl = new URL(options.returnPath || window.location.pathname || "/workspace", window.location.origin);
    if (options.projectId) returnUrl.searchParams.set("project_id", String(options.projectId));
    if (options.chapterNumber) returnUrl.searchParams.set("chapter", String(options.chapterNumber));
    const registerUrl = new URL("/register", window.location.origin);
    registerUrl.searchParams.set("return", returnUrl.pathname + returnUrl.search);
    return registerUrl.pathname + registerUrl.search;
  }

  function saveCredential(projectId, chapterNumber, data) {
    const value = {
      purchase_id: data.purchase_id,
      access_token: data.access_token,
      provider: data.provider,
      saved_at: new Date().toISOString()
    };
    localStorage.setItem(entitlementKey(projectId, chapterNumber), JSON.stringify(value));
    localStorage.setItem(`${STORAGE_PREFIX}purchase:${data.purchase_id}`, JSON.stringify(value));
    return value;
  }

  function getCredential(projectId, chapterNumber) {
    try {
      return JSON.parse(localStorage.getItem(entitlementKey(projectId, chapterNumber)) || "null");
    } catch (_) {
      return null;
    }
  }

  function paymentHeaders(projectId, chapterNumber) {
    const credential = getCredential(projectId, chapterNumber);
    if (!credential) return {};
    return {
      "X-ProjectReady-Purchase-ID": credential.purchase_id,
      "X-ProjectReady-Access-Token": credential.access_token
    };
  }

  function syncBodyModalState() {
    const openModal = document.querySelector(".pr-payment-modal:not([hidden])");
    document.body.classList.toggle("pr-payment-open", Boolean(openModal));
  }

  function closeModal(modal) {
    if (modal) modal.hidden = true;
    syncBodyModalState();
  }

  function ensureAccessGate() {
    let modal = document.getElementById("projectreadyAccessGateModal");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "projectreadyAccessGateModal";
    modal.className = "pr-payment-modal";
    modal.hidden = true;
    modal.innerHTML = `
      <div class="pr-payment-backdrop" data-pr-access-close></div>
      <section class="pr-payment-dialog pr-access-dialog" role="dialog" aria-modal="true" aria-labelledby="prAccessTitle">
        <button type="button" class="pr-payment-close" aria-label="Close" data-pr-access-close>×</button>
        <p class="pr-payment-eyebrow">Chapter access required</p>
        <h2 id="prAccessTitle">Register or unlock guided chapter development</h2>
        <p id="prAccessMessage" class="pr-access-message">This chapter requires guided-development access before working-draft development can continue.</p>
        <div id="prRegistrationState" class="pr-registration-state"></div>
        <div class="pr-access-actions">
          <a id="prRegisterLink" class="pr-access-secondary" href="/register">Register / create profile</a>
          <button id="prContinuePayment" type="button" class="pr-payment-submit">Continue to payment</button>
        </div>
        <p class="pr-payment-routing" id="prAccessBenefits">Paid chapter access includes one guided working draft, one strengthening revision, one compliance review and one editable DOCX export.</p>
      </section>`;
    document.body.appendChild(modal);

    modal.querySelectorAll("[data-pr-access-close]").forEach(el => el.addEventListener("click", () => closeModal(modal)));
    return modal;
  }

  function ensureCheckoutModal() {
    let modal = document.getElementById("projectreadyCheckoutModal");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "projectreadyCheckoutModal";
    modal.className = "pr-payment-modal";
    modal.hidden = true;
    modal.innerHTML = `
      <div class="pr-payment-backdrop" data-pr-checkout-close></div>
      <section class="pr-payment-dialog" role="dialog" aria-modal="true" aria-labelledby="prPaymentTitle">
        <button type="button" class="pr-payment-close" aria-label="Close" data-pr-checkout-close>×</button>
        <p class="pr-payment-eyebrow">Secure chapter checkout</p>
        <h2 id="prPaymentTitle">Unlock guided chapter development</h2>
        <p id="prPaymentPlan" class="pr-payment-plan"></p>
        <ul class="pr-payment-benefits" id="prPaymentBenefits">
          <li>Loading plan benefits…</li>
        </ul>
        <form id="prPaymentForm">
          <label>Email address
            <input id="prPaymentEmail" type="email" autocomplete="email" required />
          </label>
          <label>Billing country
            <select id="prPaymentCountry" required></select>
          </label>
          <p id="prPaymentRouting" class="pr-payment-routing">African billing countries use Paystack. Other countries use Stripe.</p>
          <div id="prStripeTestPanel" class="pr-stripe-test-panel" hidden>
            <strong>Stripe test mode</strong>
            <p>No real money will move. Enter the private test checkout key to continue.</p>
            <label>Private Stripe test checkout key
              <input id="prStripeTestKey" type="password" autocomplete="off" />
            </label>
          </div>
          <button type="submit" class="pr-payment-submit">Continue to secure payment</button>
          <p id="prPaymentStatus" class="pr-payment-status" aria-live="polite"></p>
        </form>
      </section>`;
    document.body.appendChild(modal);

    const select = modal.querySelector("#prPaymentCountry");
    select.innerHTML = '<option value="">Select billing country</option>' + COUNTRIES
      .map(([code, name]) => `<option value="${esc(code)}">${esc(name)}</option>`)
      .join("");

    modal.querySelectorAll("[data-pr-checkout-close]").forEach(el => el.addEventListener("click", () => closeModal(modal)));
    return modal;
  }

  function profileCountryCode(profile) {
    const supplied = String(profile?.country || "").trim().toLowerCase();
    if (!supplied) return "";
    const byCode = COUNTRIES.find(([code]) => code.toLowerCase() === supplied);
    if (byCode) return byCode[0];
    const byName = COUNTRIES.find(([, name]) => name.toLowerCase() === supplied);
    return byName ? byName[0] : "";
  }

  function prefillCheckout(modal, options = {}) {
    const profile = readRegistrationProfile();
    const email = modal.querySelector("#prPaymentEmail");
    const country = modal.querySelector("#prPaymentCountry");
    if (options.customerEmail && !email.value) email.value = options.customerEmail;
    if (profile?.email && !email.value) email.value = profile.email;
    const savedCountry = profileCountryCode(profile);
    const browserCountry = (navigator.language || "").split("-")[1]?.toUpperCase() || "";
    if (!country.value && savedCountry) country.value = savedCountry;
    if (!country.value && COUNTRIES.some(([code]) => code === browserCountry)) country.value = browserCountry;
  }

  async function openAccessGate(options, detail = {}) {
    const required = ["projectId", "chapterNumber", "academicLevel"];
    const missing = required.filter(key => options?.[key] === undefined || options?.[key] === null || options?.[key] === "");
    if (missing.length) throw new Error(`Missing access value(s): ${missing.join(", ")}`);

    const modal = ensureAccessGate();
    const profile = readRegistrationProfile();
    const message = typeof detail === "string" ? detail : (detail?.message || "This chapter requires guided-development access before working-draft development can continue.");
    modal.querySelector("#prAccessMessage").textContent = message;
    const revisionOnly = (options.purchaseMode || "chapter") === "revision_only";
    modal.querySelector("#prAccessTitle").textContent = revisionOnly ? "Unlock chapter strengthening support" : "Register or unlock guided chapter development";
    modal.querySelector("#prAccessBenefits").textContent = revisionOnly
      ? "Revision-only access includes one comprehensive strengthening revision, one compliance check and one DOCX export."
      : "Paid chapter access includes one guided working draft, one strengthening revision, one compliance review and one editable DOCX export.";
    modal.querySelector("#prRegisterLink").href = registrationUrl(options);
    modal.querySelector("#prRegisterLink").textContent = profile ? "Review registration profile" : "Register / create profile";
    modal.querySelector("#prRegistrationState").textContent = profile?.email
      ? `Registration profile found for ${profile.email}. You may continue to payment.`
      : "No registration profile was found on this device. Register first to save your details, or continue directly to payment.";

    const continueButton = modal.querySelector("#prContinuePayment");
    continueButton.onclick = async () => {
      closeModal(modal);
      await openCheckout(options);
    };

    modal.hidden = false;
    syncBodyModalState();
    window.setTimeout(() => (profile ? continueButton : modal.querySelector("#prRegisterLink"))?.focus(), 0);
  }

  async function openCheckout(options) {
    const required = ["projectId", "chapterNumber", "academicLevel"];
    const missing = required.filter(key => options?.[key] === undefined || options?.[key] === null || options?.[key] === "");
    if (missing.length) throw new Error(`Missing checkout value(s): ${missing.join(", ")}`);

    const modal = ensureCheckoutModal();
    modal.hidden = false;
    syncBodyModalState();
    prefillCheckout(modal, options);

    const status = modal.querySelector("#prPaymentStatus");
    const submit = modal.querySelector(".pr-payment-submit");
    const country = modal.querySelector("#prPaymentCountry");
    const routing = modal.querySelector("#prPaymentRouting");
    status.textContent = "Loading plan...";
    submit.disabled = true;

    let plans;
    try {
      const purchaseMode = options.purchaseMode || "chapter";
      const response = await fetch(`/api/payments/plans?level=${encodeURIComponent(options.academicLevel)}&mode=${encodeURIComponent(purchaseMode)}`, {cache: "no-store"});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail?.message || data.detail || "Could not load the chapter price.");
      plans = data;
    } catch (error) {
      status.textContent = error.message;
      return;
    }

    const plan = plans.paid_plans.find(item => item.plan_key === plans.recommended_plan);
    if (!plan) {
      status.textContent = "No paid plan is configured for this academic level.";
      return;
    }

    const paymentEnvironment = plans.payment_environment || {};
    const stripeTestMode = Boolean(paymentEnvironment.test_mode);
    const forceStripe = Boolean(paymentEnvironment.force_stripe);
    const testPanel = modal.querySelector("#prStripeTestPanel");
    const testKeyInput = modal.querySelector("#prStripeTestKey");
    testPanel.hidden = !stripeTestMode;
    testKeyInput.required = stripeTestMode;
    submit.textContent = stripeTestMode ? "Continue to Stripe test checkout" : "Continue to secure payment";

    const benefits = [];
    if (Number(plan.includes?.initial_draft || 0) > 0) benefits.push("One guided chapter working draft");
    if (Number(plan.includes?.revision || 0) > 0) benefits.push("One comprehensive chapter strengthening revision");
    if (Number(plan.includes?.compliance_check || 0) > 0) benefits.push("One compliance check");
    if (Number(plan.includes?.docx_export || 0) > 0) benefits.push("One DOCX export");
    modal.querySelector("#prPaymentBenefits").innerHTML = benefits.map(item => `<li>${esc(item)}</li>`).join("");
    modal.querySelector("#prPaymentTitle").textContent = plans.purchase_mode === "revision_only" ? "Unlock chapter strengthening support" : "Unlock guided chapter development";

    const renderPrice = () => {
      const paystack = !forceStripe && AFRICAN_COUNTRIES.has(country.value);
      const price = paystack ? (plan.paystack_price_display || plan.price_display) : plan.price_display;
      modal.querySelector("#prPaymentPlan").textContent = `${plan.name} · ${price} per ${plan.per || "chapter"}`;
      if (stripeTestMode && forceStripe) {
        routing.textContent = "Stripe test mode is forcing every billing country through Stripe. This is a simulated USD payment and no real money moves.";
      } else if (paystack) {
        routing.textContent = "This billing country will use Paystack and charge the displayed GHS amount.";
      } else {
        routing.textContent = stripeTestMode
          ? "This checkout uses Stripe test mode. No real money moves."
          : "This billing country will use Stripe and charge the displayed USD amount.";
      }
    };
    country.onchange = renderPrice;
    renderPrice();
    status.textContent = "";
    submit.disabled = false;

    const form = modal.querySelector("#prPaymentForm");
    form.onsubmit = async (event) => {
      event.preventDefault();
      submit.disabled = true;
      status.textContent = "Creating secure checkout...";
      window.ProjectReadyWorkspace?.saveSnapshot?.({reason: "payment_form_submit"});
      const payload = {
        email: modal.querySelector("#prPaymentEmail").value.trim(),
        billing_country: country.value,
        academic_level: options.academicLevel,
        project_id: String(options.projectId),
        chapter_number: Number(options.chapterNumber),
        chapter_title: options.chapterTitle || `Chapter ${options.chapterNumber}`,
        plan_key: plan.plan_key,
        purchase_mode: options.purchaseMode || "chapter",
        return_path: options.returnPath || window.location.pathname || "/workspace",
        test_access_key: stripeTestMode ? testKeyInput.value.trim() : ""
      };
      try {
        if (stripeTestMode && !payload.test_access_key) {
          throw new Error("Enter the private Stripe test checkout key.");
        }
        const response = await fetch("/api/payments/checkout", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = typeof data.detail === "string" ? data.detail : (data.detail?.message || "Checkout could not start.");
          throw new Error(detail);
        }
        saveCredential(payload.project_id, payload.chapter_number, data);
        window.ProjectReadyWorkspace?.saveSnapshot?.({reason: "before_payment_redirect"});
        if (!data.checkout_url) throw new Error("The payment provider did not return a checkout URL.");
        window.location.assign(data.checkout_url);
      } catch (error) {
        status.textContent = error.message;
        submit.disabled = false;
      }
    };
  }

  async function checkEntitlement(projectId, chapterNumber) {
    const credential = getCredential(projectId, chapterNumber);
    if (!credential) return {ok: false, allowed: false, reason: "not_stored"};
    const response = await fetch("/api/payments/entitlement-status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(credential)
    });
    const data = await response.json().catch(() => ({}));
    return response.ok ? data : {ok: false, allowed: false, detail: data.detail};
  }

  function bindCheckoutButtons() {
    document.querySelectorAll("[data-projectready-checkout]").forEach(button => {
      if (button.dataset.prBound === "1") return;
      button.dataset.prBound = "1";
      button.addEventListener("click", () => openAccessGate({
        projectId: button.dataset.projectId,
        chapterNumber: Number(button.dataset.chapterNumber),
        chapterTitle: button.dataset.chapterTitle || "",
        academicLevel: button.dataset.academicLevel,
        purchaseMode: button.dataset.purchaseMode || "chapter",
        returnPath: button.dataset.returnPath || window.location.pathname
      }).catch(error => window.alert(error.message)));
    });
  }

  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    document.querySelectorAll(".pr-payment-modal:not([hidden])").forEach(closeModal);
  });

  window.ProjectReadyPayments = {
    openAccessGate,
    openCheckout,
    saveCredential,
    getCredential,
    paymentHeaders,
    checkEntitlement,
    bindCheckoutButtons,
    hasRegistrationProfile,
    readRegistrationProfile,
    registrationUrl
  };
  document.addEventListener("DOMContentLoaded", bindCheckoutButtons);
})();
