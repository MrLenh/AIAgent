function agentApp() {
  return {
    tab: 'status',
    tabs: [
      { id: 'status',   label: 'Status',      icon: '◉' },
      { id: 'seo',      label: 'SEO Article', icon: '✎' },
      { id: 'listing',  label: 'Listing',     icon: '✦' },
      { id: 'analyze',  label: 'Analysis',    icon: '∴' },
      { id: 'audit',    label: 'Audit',       icon: '◎' },
      { id: 'history',  label: 'History',     icon: '☰' },
      { id: 'settings', label: 'Settings',    icon: '⚙' },
    ],
    status: { llm_configured: false, env: {} },

    seo: {
      topic: '', primary_keyword: '', secondary_keywords_raw: '',
      audience: 'general readers', word_count: 1200, tone: 'informative and friendly',
      reference: '',
      internal_source: 'none',
      external_raw: '',
      check_duplicates: true,
      auto_publish: false,
      publish_platform: 'wordpress',
      publish_status: 'draft',
      loading: false, result: null, error: '',
      publishing: false, publishResult: '',
      showPreview: false,
    },

    history: {
      items: [],
      selected: null,
      showPreview: false,
      publishing: false,
      publishStatus: 'draft',
      publishResult: '',
      publishOk: false,
    },

    audit: {
      step: 'crawl',  // crawl -> gsc -> ahrefs -> run -> plan -> execute
      site: '',
      posts: [],
      loadingCrawl: false,
      gscSite: '',
      gscDays: 28,
      gscQueries: [],
      gscPages: [],
      loadingGsc: false,
      ahrefsTarget: '',
      ahrefsCompetitors: '',
      ahrefsCountry: 'us',
      competitorKeywords: [],
      organicCompetitors: [],
      loadingAhrefs: false,
      report: null,
      loadingReport: false,
      plan: null,
      planTimeframe: 'next 30 days',
      planMaxItems: 10,
      loadingPlan: false,
      plans: [],
      selectedPlan: null,
      executing: {},     // {item_index: bool}
      executeStatus: {}, // {item_index: message}
      autoPublish: true,
      publishStatus: 'draft',
      rankingKeywords: '',
      rankingResult: null,
      loadingRanking: false,
    },

    listing: {
      platform: 'manual', product_id: null,
      current_title: '', current_description: '',
      primary_keyword: '', target_audience: 'online shoppers',
      attributes_raw: '',
      fetching: false, loading: false, applying: false,
      result: null, error: '', applyResult: '',
    },

    analyze: {
      mode: 'upload', file: null,
      db_url: '', sql: '',
      text: '',
      question: '',
      loading: false, result: '', error: '',
    },

    settings: {
      llm: { provider: '', model: '', api_key: '' },
      shopify: { shop: '', access_token: '' },
      wordpress: { base_url: '', username: '', app_password: '' },
      woocommerce: { base_url: '', consumer_key: '', consumer_secret: '' },
      gsc: { site_url: '', service_account_json: '' },
      ahrefs: { api_token: '' },
      testResult: {},
      testingLLM: false,
      geminiModels: [],
      saved: false,
    },

    async init() {
      this.loadSettings();
      await this.refreshStatus();
      this.$watch('tab', (t) => {
        if (t === 'history') this.loadHistory();
        if (t === 'audit') this.loadPlans();
      });
    },

    async refreshStatus() {
      try {
        const r = await fetch('/api/status');
        this.status = await r.json();
      } catch (e) {
        this.status = { llm_configured: false, env: {} };
      }
    },

    statusItems() {
      const e = this.status.env || {};
      return [
        { key: 'llm',    label: 'LLM provider',  ok: this.status.llm_configured, detail: e.llm_provider || '(none)' },
        { key: 'anth',   label: 'Anthropic key', ok: e.has_anthropic,  detail: e.has_anthropic ? 'configured' : 'missing' },
        { key: 'oai',    label: 'OpenAI key',    ok: e.has_openai,     detail: e.has_openai ? 'configured' : 'missing' },
        { key: 'gem',    label: 'Gemini key',    ok: e.has_gemini,     detail: e.has_gemini ? 'configured' : 'missing' },
        { key: 'shop',   label: 'Shopify',       ok: e.has_shopify,    detail: e.has_shopify ? 'env configured' : 'no env creds' },
        { key: 'wp',     label: 'WordPress',     ok: e.has_wordpress,  detail: e.has_wordpress ? 'env configured' : 'no env creds' },
        { key: 'woo',    label: 'WooCommerce',   ok: e.has_woocommerce, detail: e.has_woocommerce ? 'env configured' : 'no env creds' },
        { key: 'db',     label: 'Database URL',  ok: e.has_database,   detail: e.has_database ? 'configured' : 'missing' },
      ];
    },

    llmPayload() {
      const s = this.settings.llm;
      if (!s.provider && !s.api_key) return null;
      return { provider: s.provider || null, model: s.model || null, api_key: s.api_key || null };
    },

    async postJSON(path, body) {
      const r = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      return data;
    },

    // ---- SEO ----
    async runSEO() {
      this.seo.loading = true; this.seo.error = ''; this.seo.result = null;
      try {
        const sources = this.seo.reference.trim()
          ? [{ type: 'text', content: this.seo.reference }] : [];

        let internal_links = null;
        if (this.seo.internal_source !== 'none') {
          const creds = this.credsFor(this.seo.internal_source);
          internal_links = { source: this.seo.internal_source, creds, limit: 5 };
        }

        const external_links = this.seo.external_raw
          .split('\n').map(s => s.trim()).filter(Boolean);

        let publish = null;
        if (this.seo.auto_publish) {
          publish = {
            platform: this.seo.publish_platform,
            status: this.seo.publish_status,
            creds: this.credsFor(this.seo.publish_platform),
          };
        }

        const body = {
          topic: this.seo.topic,
          primary_keyword: this.seo.primary_keyword,
          secondary_keywords: this.seo.secondary_keywords_raw
            .split(',').map(s => s.trim()).filter(Boolean),
          audience: this.seo.audience,
          word_count: this.seo.word_count,
          tone: this.seo.tone,
          sources,
          internal_links,
          external_links,
          check_duplicates: this.seo.check_duplicates,
          publish,
          save_history: true,
          llm: this.llmPayload(),
        };
        this.seo.result = await this.postJSON('/api/seo-article', body);
      } catch (e) { this.seo.error = e.message; }
      finally { this.seo.loading = false; }
    },

    credsFor(platform) {
      if (platform === 'wordpress' || platform === 'wp') {
        const wp = this.settings.wordpress;
        if (wp.base_url && wp.username && wp.app_password) return { ...wp };
      }
      if (platform === 'shopify') {
        const s = this.settings.shopify;
        if (s.shop && s.access_token) return { ...s };
      }
      return null;  // backend falls back to env
    },

    async publishToWP() {
      const wp = this.settings.wordpress;
      if (!wp.base_url || !wp.username || !wp.app_password) {
        this.seo.publishResult = 'Cần cấu hình WordPress trong Settings';
        return;
      }
      this.seo.publishing = true; this.seo.publishResult = '';
      try {
        const r = await this.postJSON('/api/wordpress/publish', {
          ...wp,
          title: this.seo.result.title,
          content: this.seo.result.body_html,
          excerpt: this.seo.result.meta_description,
          status: this.seo.publish_status,
        });
        this.seo.publishResult = `Published: ${r.link || r.id || 'ok'}`;
      } catch (e) { this.seo.publishResult = `Error: ${e.message}`; }
      finally { this.seo.publishing = false; }
    },

    // ---- Audit ----
    async crawlSite() {
      this.audit.loadingCrawl = true;
      try {
        const wp = this.settings.wordpress;
        const useWP = this.audit.site === 'wordpress' || (!this.audit.site && wp.base_url);
        const body = useWP
          ? { source: 'wordpress', wp, limit: 100 }
          : { source: 'sitemap', base_url: this.audit.site, limit: 100 };
        const r = await this.postJSON('/api/audit/crawl', body);
        this.audit.posts = r.posts || [];
      } catch (e) { alert('Crawl failed: ' + e.message); }
      finally { this.audit.loadingCrawl = false; }
    },

    async loadGSC() {
      this.audit.loadingGsc = true;
      try {
        const saJson = this.settings.gsc.service_account_json;
        if (!saJson) { alert('Cần service account JSON trong Settings'); return; }
        const body = {
          site_url: this.audit.gscSite || this.settings.gsc.site_url,
          service_account_json: JSON.parse(saJson),
          days: this.audit.gscDays,
          row_limit: 500,
        };
        const qData = await this.postJSON('/api/audit/gsc/query', { ...body, dimensions: ['query'] });
        this.audit.gscQueries = qData.rows || [];
        const pData = await this.postJSON('/api/audit/gsc/query', { ...body, dimensions: ['page'] });
        this.audit.gscPages = pData.rows || [];
      } catch (e) { alert('GSC error: ' + e.message); }
      finally { this.audit.loadingGsc = false; }
    },

    async loadAhrefs() {
      const tok = this.settings.ahrefs.api_token;
      if (!tok) { alert('Cần Ahrefs API token trong Settings'); return; }
      this.audit.loadingAhrefs = true;
      try {
        const target = this.audit.ahrefsTarget;
        const country = this.audit.ahrefsCountry || 'us';
        const compResp = await this.postJSON('/api/audit/ahrefs/competitors', {
          api_token: tok, target, country, limit: 10,
        });
        this.audit.organicCompetitors = compResp.competitors || [];
        const compList = this.audit.ahrefsCompetitors
          .split(',').map(s => s.trim()).filter(Boolean);
        if (target && compList.length) {
          const gap = await this.postJSON('/api/audit/ahrefs/content-gap', {
            api_token: tok, target, competitors: compList, country, limit: 100,
          });
          this.audit.competitorKeywords = gap.keywords || [];
        }
      } catch (e) { alert('Ahrefs error: ' + e.message); }
      finally { this.audit.loadingAhrefs = false; }
    },

    async runAudit() {
      this.audit.loadingReport = true; this.audit.report = null;
      try {
        this.audit.report = await this.postJSON('/api/audit/run', {
          blog_posts: this.audit.posts,
          gsc_queries: this.audit.gscQueries,
          gsc_pages: this.audit.gscPages,
          competitor_keywords: this.audit.competitorKeywords,
          competitors: this.audit.organicCompetitors,
          llm: this.llmPayload(),
        });
      } catch (e) { alert('Audit error: ' + e.message); }
      finally { this.audit.loadingReport = false; }
    },

    async runPlan() {
      if (!this.audit.report) { alert('Chạy audit trước'); return; }
      this.audit.loadingPlan = true;
      try {
        const r = await this.postJSON('/api/audit/plan', {
          audit: this.audit.report,
          timeframe: this.audit.planTimeframe,
          inventory_urls: this.audit.posts.map(p => p.url).filter(Boolean),
          max_items: this.audit.planMaxItems,
          site: this.audit.gscSite || this.audit.ahrefsTarget,
          save: true,
          llm: this.llmPayload(),
        });
        this.audit.plan = r;
        await this.loadPlans();
      } catch (e) { alert('Plan error: ' + e.message); }
      finally { this.audit.loadingPlan = false; }
    },

    async loadPlans() {
      try {
        const r = await fetch('/api/audit/plans');
        this.audit.plans = (await r.json()).items || [];
      } catch (e) {}
    },

    async openPlan(id) {
      try {
        const r = await fetch('/api/audit/plans/' + id);
        this.audit.selectedPlan = await r.json();
      } catch (e) {}
    },

    async executePlanItem(itemIndex) {
      if (!this.audit.selectedPlan) return;
      this.audit.executing = { ...this.audit.executing, [itemIndex]: true };
      try {
        const publish = this.audit.autoPublish
          ? {
              platform: 'wordpress',
              status: this.audit.publishStatus,
              creds: this.credsFor('wordpress'),
            }
          : null;
        const body = {
          plan_id: this.audit.selectedPlan.id,
          item_index: itemIndex,
          publish,
          internal_links: { source: 'wordpress', creds: this.credsFor('wordpress'), limit: 5 },
          llm: this.llmPayload(),
        };
        const r = await this.postJSON('/api/audit/plan/execute', body);
        this.audit.executeStatus = {
          ...this.audit.executeStatus,
          [itemIndex]: `OK · ${r.result.published ? 'published to ' + r.result.published.url : 'saved as draft'}`,
        };
        await this.openPlan(this.audit.selectedPlan.id);
      } catch (e) {
        this.audit.executeStatus = { ...this.audit.executeStatus, [itemIndex]: 'Error: ' + e.message };
      } finally {
        this.audit.executing = { ...this.audit.executing, [itemIndex]: false };
      }
    },

    async rankingSnapshot() {
      const saJson = this.settings.gsc.service_account_json;
      if (!saJson) { alert('Cần GSC service account JSON'); return; }
      this.audit.loadingRanking = true;
      try {
        const kws = this.audit.rankingKeywords
          .split('\n').map(s => s.trim()).filter(Boolean);
        const r = await this.postJSON('/api/audit/ranking/snapshot', {
          site: this.audit.gscSite || this.settings.gsc.site_url,
          service_account_json: JSON.parse(saJson),
          keywords: kws,
          days: 7,
        });
        this.audit.rankingResult = r;
      } catch (e) { alert('Ranking error: ' + e.message); }
      finally { this.audit.loadingRanking = false; }
    },

    // ---- History ----
    async loadHistory() {
      try {
        const r = await fetch('/api/history?limit=200');
        const data = await r.json();
        this.history.items = data.items || [];
      } catch (e) {}
    },
    async openHistoryItem(id) {
      try {
        const r = await fetch(`/api/history/${id}`);
        this.history.selected = await r.json();
        this.history.showPreview = false;
        this.history.publishResult = '';
      } catch (e) {}
    },
    async deleteHistoryItem(id) {
      if (!confirm('Xoá bài này?')) return;
      await fetch(`/api/history/${id}`, { method: 'DELETE' });
      this.history.selected = null;
      await this.loadHistory();
    },
    async republish(platform) {
      if (!this.history.selected) return;
      this.history.publishing = true; this.history.publishResult = '';
      try {
        const r = await this.postJSON(`/api/history/${this.history.selected.id}/publish`, {
          platform, status: this.history.publishStatus,
          creds: this.credsFor(platform),
        });
        this.history.publishOk = true;
        this.history.publishResult = `Published: ${r.url || r.id}`;
        await this.openHistoryItem(this.history.selected.id);
      } catch (e) {
        this.history.publishOk = false;
        this.history.publishResult = `Error: ${e.message}`;
      } finally { this.history.publishing = false; }
    },

    // ---- Listing ----
    async fetchProduct() {
      this.listing.fetching = true; this.listing.error = '';
      try {
        if (this.listing.platform === 'shopify') {
          const s = this.settings.shopify;
          const p = await this.postJSON('/api/shopify/product', { ...s, product_id: this.listing.product_id });
          this.listing.current_title = p.title || '';
          this.listing.current_description = p.body_html || '';
          this.listing.attributes_raw = `vendor: ${p.vendor || ''}\ntype: ${p.product_type || ''}\ntags: ${p.tags || ''}`;
        } else if (this.listing.platform === 'woocommerce') {
          const w = this.settings.woocommerce;
          const p = await this.postJSON('/api/woocommerce/product', { ...w, product_id: this.listing.product_id });
          this.listing.current_title = p.name || '';
          this.listing.current_description = p.description || '';
          this.listing.attributes_raw = (p.categories || []).map(c => `category: ${c.name}`).join('\n');
        }
      } catch (e) { this.listing.error = e.message; }
      finally { this.listing.fetching = false; }
    },

    async runListing() {
      this.listing.loading = true; this.listing.error = ''; this.listing.result = null; this.listing.applyResult = '';
      try {
        const attrs = {};
        this.listing.attributes_raw.split('\n').forEach(line => {
          const idx = line.indexOf(':');
          if (idx > 0) attrs[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
        });
        this.listing.result = await this.postJSON('/api/optimize-listing', {
          current_title: this.listing.current_title,
          current_description: this.listing.current_description,
          product_attributes: attrs,
          primary_keyword: this.listing.primary_keyword || null,
          target_audience: this.listing.target_audience,
          llm: this.llmPayload(),
        });
      } catch (e) { this.listing.error = e.message; }
      finally { this.listing.loading = false; }
    },

    async applyListing() {
      this.listing.applying = true; this.listing.applyResult = '';
      try {
        if (this.listing.platform === 'shopify') {
          const s = this.settings.shopify;
          await this.postJSON('/api/shopify/apply-listing', {
            ...s, product_id: this.listing.product_id, listing: this.listing.result,
          });
          this.listing.applyResult = 'Applied to Shopify';
        } else if (this.listing.platform === 'woocommerce') {
          const w = this.settings.woocommerce;
          await this.postJSON('/api/woocommerce/apply-listing', {
            ...w, product_id: this.listing.product_id, listing: this.listing.result,
          });
          this.listing.applyResult = 'Applied to WooCommerce';
        }
      } catch (e) { this.listing.applyResult = `Error: ${e.message}`; }
      finally { this.listing.applying = false; }
    },

    // ---- Analysis ----
    async runAnalyze() {
      this.analyze.loading = true; this.analyze.error = ''; this.analyze.result = '';
      try {
        if (this.analyze.mode === 'upload') {
          if (!this.analyze.file) throw new Error('Chọn file CSV');
          const fd = new FormData();
          fd.append('question', this.analyze.question);
          fd.append('file', this.analyze.file);
          const s = this.settings.llm;
          if (s.provider) fd.append('provider', s.provider);
          if (s.model) fd.append('model', s.model);
          if (s.api_key) fd.append('api_key', s.api_key);
          const r = await fetch('/api/analyze-upload', { method: 'POST', body: fd });
          const data = await r.json();
          if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
          this.analyze.result = data.report;
        } else {
          let sources;
          if (this.analyze.mode === 'sql') {
            sources = [{ type: 'database', url: this.analyze.db_url, query: this.analyze.sql }];
          } else {
            sources = [{ type: 'text', content: this.analyze.text }];
          }
          const r = await this.postJSON('/api/analyze', {
            question: this.analyze.question, sources, llm: this.llmPayload(),
          });
          this.analyze.result = r.report;
        }
      } catch (e) { this.analyze.error = e.message; }
      finally { this.analyze.loading = false; }
    },

    // ---- Settings ----
    loadSettings() {
      try {
        const s = localStorage.getItem('aiagent.settings');
        if (s) {
          const parsed = JSON.parse(s);
          this.settings = { ...this.settings, ...parsed, testResult: {}, saved: false };
        }
      } catch {}
    },
    saveSettings() {
      const { testResult, saved, ...rest } = this.settings;
      localStorage.setItem('aiagent.settings', JSON.stringify(rest));
      this.settings.saved = true;
      setTimeout(() => { this.settings.saved = false; }, 1500);
    },
    clearSettings() {
      localStorage.removeItem('aiagent.settings');
      this.settings = {
        llm: { provider: '', model: '', api_key: '' },
        shopify: { shop: '', access_token: '' },
        wordpress: { base_url: '', username: '', app_password: '' },
        woocommerce: { base_url: '', consumer_key: '', consumer_secret: '' },
        gsc: { site_url: '', service_account_json: '' },
        ahrefs: { api_token: '' },
        testResult: {}, testingLLM: false, geminiModels: [], saved: false,
      };
    },
    async listGeminiModels() {
      try {
        const r = await this.postJSON('/api/gemini/models', { api_key: this.settings.llm.api_key || null });
        this.settings.geminiModels = r.models || [];
        this.settings.testResult = { ...this.settings.testResult, llm: { ok: true, provider: 'gemini', model: `${r.models.length} models`, text: r.models.slice(0, 5).map(m => m.name).join(', ') } };
      } catch (e) {
        this.settings.testResult = { ...this.settings.testResult, llm: { ok: false, error: e.message } };
      }
    },

    async testLLM() {
      this.settings.testingLLM = true;
      try {
        const r = await this.postJSON('/api/llm-test', { llm: this.llmPayload() });
        this.settings.testResult = { ...this.settings.testResult, llm: r };
      } catch (e) {
        this.settings.testResult = { ...this.settings.testResult, llm: { ok: false, error: e.message } };
      } finally {
        this.settings.testingLLM = false;
      }
    },

    async testPlatform(platform) {
      const creds = this.settings[platform];
      try {
        const r = await this.postJSON('/api/platforms/test', { platform, creds });
        this.settings.testResult = { ...this.settings.testResult, [platform]: r };
      } catch (e) {
        this.settings.testResult = { ...this.settings.testResult, [platform]: { ok: false, error: e.message } };
      }
    },

    copyToClipboard(text) {
      navigator.clipboard.writeText(text);
    },
  };
}
