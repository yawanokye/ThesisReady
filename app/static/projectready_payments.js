/* ProjectReady AI chapter checkout UI. */
(() => {
  "use strict";
  const COUNTRIES = [["AF", "Afghanistan"], ["AL", "Albania"], ["DZ", "Algeria"], ["AS", "American Samoa"], ["AD", "Andorra"], ["AO", "Angola"], ["AI", "Anguilla"], ["AQ", "Antarctica"], ["AG", "Antigua and Barbuda"], ["AR", "Argentina"], ["AM", "Armenia"], ["AW", "Aruba"], ["AU", "Australia"], ["AT", "Austria"], ["AZ", "Azerbaijan"], ["BS", "Bahamas"], ["BH", "Bahrain"], ["BD", "Bangladesh"], ["BB", "Barbados"], ["BY", "Belarus"], ["BE", "Belgium"], ["BZ", "Belize"], ["BJ", "Benin"], ["BM", "Bermuda"], ["BT", "Bhutan"], ["BO", "Bolivia, Plurinational State of"], ["BQ", "Bonaire, Sint Eustatius and Saba"], ["BA", "Bosnia and Herzegovina"], ["BW", "Botswana"], ["BV", "Bouvet Island"], ["BR", "Brazil"], ["IO", "British Indian Ocean Territory"], ["BN", "Brunei Darussalam"], ["BG", "Bulgaria"], ["BF", "Burkina Faso"], ["BI", "Burundi"], ["CV", "Cabo Verde"], ["KH", "Cambodia"], ["CM", "Cameroon"], ["CA", "Canada"], ["KY", "Cayman Islands"], ["CF", "Central African Republic"], ["TD", "Chad"], ["CL", "Chile"], ["CN", "China"], ["CX", "Christmas Island"], ["CC", "Cocos (Keeling) Islands"], ["CO", "Colombia"], ["KM", "Comoros"], ["CG", "Congo"], ["CD", "Congo, The Democratic Republic of the"], ["CK", "Cook Islands"], ["CR", "Costa Rica"], ["HR", "Croatia"], ["CU", "Cuba"], ["CW", "Curaçao"], ["CY", "Cyprus"], ["CZ", "Czechia"], ["CI", "Côte d'Ivoire"], ["DK", "Denmark"], ["DJ", "Djibouti"], ["DM", "Dominica"], ["DO", "Dominican Republic"], ["EC", "Ecuador"], ["EG", "Egypt"], ["SV", "El Salvador"], ["GQ", "Equatorial Guinea"], ["ER", "Eritrea"], ["EE", "Estonia"], ["SZ", "Eswatini"], ["ET", "Ethiopia"], ["FK", "Falkland Islands (Malvinas)"], ["FO", "Faroe Islands"], ["FJ", "Fiji"], ["FI", "Finland"], ["FR", "France"], ["GF", "French Guiana"], ["PF", "French Polynesia"], ["TF", "French Southern Territories"], ["GA", "Gabon"], ["GM", "Gambia"], ["GE", "Georgia"], ["DE", "Germany"], ["GH", "Ghana"], ["GI", "Gibraltar"], ["GR", "Greece"], ["GL", "Greenland"], ["GD", "Grenada"], ["GP", "Guadeloupe"], ["GU", "Guam"], ["GT", "Guatemala"], ["GG", "Guernsey"], ["GN", "Guinea"], ["GW", "Guinea-Bissau"], ["GY", "Guyana"], ["HT", "Haiti"], ["HM", "Heard Island and McDonald Islands"], ["VA", "Holy See (Vatican City State)"], ["HN", "Honduras"], ["HK", "Hong Kong"], ["HU", "Hungary"], ["IS", "Iceland"], ["IN", "India"], ["ID", "Indonesia"], ["IR", "Iran, Islamic Republic of"], ["IQ", "Iraq"], ["IE", "Ireland"], ["IM", "Isle of Man"], ["IL", "Israel"], ["IT", "Italy"], ["JM", "Jamaica"], ["JP", "Japan"], ["JE", "Jersey"], ["JO", "Jordan"], ["KZ", "Kazakhstan"], ["KE", "Kenya"], ["KI", "Kiribati"], ["KP", "Korea, Democratic People's Republic of"], ["KR", "Korea, Republic of"], ["KW", "Kuwait"], ["KG", "Kyrgyzstan"], ["LA", "Lao People's Democratic Republic"], ["LV", "Latvia"], ["LB", "Lebanon"], ["LS", "Lesotho"], ["LR", "Liberia"], ["LY", "Libya"], ["LI", "Liechtenstein"], ["LT", "Lithuania"], ["LU", "Luxembourg"], ["MO", "Macao"], ["MG", "Madagascar"], ["MW", "Malawi"], ["MY", "Malaysia"], ["MV", "Maldives"], ["ML", "Mali"], ["MT", "Malta"], ["MH", "Marshall Islands"], ["MQ", "Martinique"], ["MR", "Mauritania"], ["MU", "Mauritius"], ["YT", "Mayotte"], ["MX", "Mexico"], ["FM", "Micronesia, Federated States of"], ["MD", "Moldova, Republic of"], ["MC", "Monaco"], ["MN", "Mongolia"], ["ME", "Montenegro"], ["MS", "Montserrat"], ["MA", "Morocco"], ["MZ", "Mozambique"], ["MM", "Myanmar"], ["NA", "Namibia"], ["NR", "Nauru"], ["NP", "Nepal"], ["NL", "Netherlands"], ["NC", "New Caledonia"], ["NZ", "New Zealand"], ["NI", "Nicaragua"], ["NE", "Niger"], ["NG", "Nigeria"], ["NU", "Niue"], ["NF", "Norfolk Island"], ["MK", "North Macedonia"], ["MP", "Northern Mariana Islands"], ["NO", "Norway"], ["OM", "Oman"], ["PK", "Pakistan"], ["PW", "Palau"], ["PS", "Palestine, State of"], ["PA", "Panama"], ["PG", "Papua New Guinea"], ["PY", "Paraguay"], ["PE", "Peru"], ["PH", "Philippines"], ["PN", "Pitcairn"], ["PL", "Poland"], ["PT", "Portugal"], ["PR", "Puerto Rico"], ["QA", "Qatar"], ["RO", "Romania"], ["RU", "Russian Federation"], ["RW", "Rwanda"], ["RE", "Réunion"], ["BL", "Saint Barthélemy"], ["SH", "Saint Helena, Ascension and Tristan da Cunha"], ["KN", "Saint Kitts and Nevis"], ["LC", "Saint Lucia"], ["MF", "Saint Martin (French part)"], ["PM", "Saint Pierre and Miquelon"], ["VC", "Saint Vincent and the Grenadines"], ["WS", "Samoa"], ["SM", "San Marino"], ["ST", "Sao Tome and Principe"], ["SA", "Saudi Arabia"], ["SN", "Senegal"], ["RS", "Serbia"], ["SC", "Seychelles"], ["SL", "Sierra Leone"], ["SG", "Singapore"], ["SX", "Sint Maarten (Dutch part)"], ["SK", "Slovakia"], ["SI", "Slovenia"], ["SB", "Solomon Islands"], ["SO", "Somalia"], ["ZA", "South Africa"], ["GS", "South Georgia and the South Sandwich Islands"], ["SS", "South Sudan"], ["ES", "Spain"], ["LK", "Sri Lanka"], ["SD", "Sudan"], ["SR", "Suriname"], ["SJ", "Svalbard and Jan Mayen"], ["SE", "Sweden"], ["CH", "Switzerland"], ["SY", "Syrian Arab Republic"], ["TW", "Taiwan, Province of China"], ["TJ", "Tajikistan"], ["TZ", "Tanzania, United Republic of"], ["TH", "Thailand"], ["TL", "Timor-Leste"], ["TG", "Togo"], ["TK", "Tokelau"], ["TO", "Tonga"], ["TT", "Trinidad and Tobago"], ["TN", "Tunisia"], ["TM", "Turkmenistan"], ["TC", "Turks and Caicos Islands"], ["TV", "Tuvalu"], ["TR", "Türkiye"], ["UG", "Uganda"], ["UA", "Ukraine"], ["AE", "United Arab Emirates"], ["GB", "United Kingdom"], ["US", "United States"], ["UM", "United States Minor Outlying Islands"], ["UY", "Uruguay"], ["UZ", "Uzbekistan"], ["VU", "Vanuatu"], ["VE", "Venezuela, Bolivarian Republic of"], ["VN", "Viet Nam"], ["VG", "Virgin Islands, British"], ["VI", "Virgin Islands, U.S."], ["WF", "Wallis and Futuna"], ["EH", "Western Sahara"], ["YE", "Yemen"], ["ZM", "Zambia"], ["ZW", "Zimbabwe"], ["AX", "Åland Islands"]];
  const STORAGE_PREFIX = "projectready-entitlement:";

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[ch]);

  function entitlementKey(projectId, chapterNumber) {
    return `${STORAGE_PREFIX}${projectId}:chapter-${chapterNumber}`;
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

  function ensureModal() {
    let modal = document.getElementById("projectreadyCheckoutModal");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "projectreadyCheckoutModal";
    modal.className = "pr-payment-modal";
    modal.hidden = true;
    modal.innerHTML = `
      <div class="pr-payment-backdrop" data-pr-close></div>
      <section class="pr-payment-dialog" role="dialog" aria-modal="true" aria-labelledby="prPaymentTitle">
        <button type="button" class="pr-payment-close" aria-label="Close" data-pr-close>×</button>
        <p class="pr-payment-eyebrow">Secure chapter checkout</p>
        <h2 id="prPaymentTitle">Unlock this chapter</h2>
        <p id="prPaymentPlan" class="pr-payment-plan"></p>
        <ul class="pr-payment-benefits">
          <li>One complete chapter draft</li>
          <li>One chapter revision</li>
          <li>One compliance check</li>
          <li>One DOCX export</li>
        </ul>
        <form id="prPaymentForm">
          <label>Email address
            <input id="prPaymentEmail" type="email" autocomplete="email" required />
          </label>
          <label>Billing country
            <select id="prPaymentCountry" required></select>
          </label>
          <p class="pr-payment-routing">African billing countries use Paystack. Other countries use Stripe.</p>
          <button type="submit" class="pr-payment-submit">Continue to secure payment</button>
          <p id="prPaymentStatus" class="pr-payment-status" aria-live="polite"></p>
        </form>
      </section>`;
    document.body.appendChild(modal);

    const select = modal.querySelector("#prPaymentCountry");
    select.innerHTML = '<option value="">Select billing country</option>' + COUNTRIES
      .map(([code, name]) => `<option value="${esc(code)}">${esc(name)}</option>`)
      .join("");
    const browserCountry = (navigator.language || "").split("-")[1];
    if (browserCountry && COUNTRIES.some(([code]) => code === browserCountry.toUpperCase())) {
      select.value = browserCountry.toUpperCase();
    }

    modal.querySelectorAll("[data-pr-close]").forEach(el => el.addEventListener("click", () => {
      modal.hidden = true;
      document.body.classList.remove("pr-payment-open");
    }));
    return modal;
  }

  async function openCheckout(options) {
    const required = ["projectId", "chapterNumber", "academicLevel"];
    const missing = required.filter(key => options?.[key] === undefined || options?.[key] === null || options?.[key] === "");
    if (missing.length) throw new Error(`Missing checkout value(s): ${missing.join(", ")}`);

    const modal = ensureModal();
    modal.hidden = false;
    document.body.classList.add("pr-payment-open");
    const status = modal.querySelector("#prPaymentStatus");
    const submit = modal.querySelector(".pr-payment-submit");
    status.textContent = "Loading plan…";
    submit.disabled = true;

    let plans;
    try {
      const response = await fetch(`/api/payments/plans?level=${encodeURIComponent(options.academicLevel)}`);
      if (!response.ok) throw new Error("Could not load the chapter price.");
      plans = await response.json();
    } catch (error) {
      status.textContent = error.message;
      return;
    }

    const plan = plans.paid_plans.find(item => item.plan_key === plans.recommended_plan);
    if (!plan) {
      status.textContent = "No paid plan is configured for this academic level.";
      return;
    }
    modal.querySelector("#prPaymentPlan").textContent = `${plan.name} · ${plan.price_display} per chapter`;
    status.textContent = "";
    submit.disabled = false;

    const form = modal.querySelector("#prPaymentForm");
    form.onsubmit = async (event) => {
      event.preventDefault();
      submit.disabled = true;
      status.textContent = "Creating secure checkout…";
      const payload = {
        email: modal.querySelector("#prPaymentEmail").value.trim(),
        billing_country: modal.querySelector("#prPaymentCountry").value,
        academic_level: options.academicLevel,
        project_id: String(options.projectId),
        chapter_number: Number(options.chapterNumber),
        chapter_title: options.chapterTitle || `Chapter ${options.chapterNumber}`,
        plan_key: plan.plan_key
      };
      try {
        const response = await fetch("/api/payments/checkout", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
          const detail = typeof data.detail === "string" ? data.detail : (data.detail?.message || "Checkout could not start.");
          throw new Error(detail);
        }
        saveCredential(payload.project_id, payload.chapter_number, data);
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
    const data = await response.json();
    return response.ok ? data : {ok: false, allowed: false, detail: data.detail};
  }

  function bindCheckoutButtons() {
    document.querySelectorAll("[data-projectready-checkout]").forEach(button => {
      if (button.dataset.prBound === "1") return;
      button.dataset.prBound = "1";
      button.addEventListener("click", () => openCheckout({
        projectId: button.dataset.projectId,
        chapterNumber: Number(button.dataset.chapterNumber),
        chapterTitle: button.dataset.chapterTitle || "",
        academicLevel: button.dataset.academicLevel
      }).catch(error => window.alert(error.message)));
    });
  }

  window.ProjectReadyPayments = {
    openCheckout,
    getCredential,
    paymentHeaders,
    checkEntitlement,
    bindCheckoutButtons
  };
  document.addEventListener("DOMContentLoaded", bindCheckoutButtons);
})();
