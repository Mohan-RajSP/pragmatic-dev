# AWS Deployment Runbook — Pragmatic-dev

End-to-end guide to deploy on a **fresh AWS account**, in order:
account/IAM → **GoDaddy DNS + records** → certificates → S3 → CloudFront → **local
test checkpoint** → ECR → Redis → networking → ECS. Companion to
[`deployment-plan.md`](./deployment-plan.md) (high-level decisions).

> **Regions:** put app resources in **`ap-south-1` (Mumbai)**. ⚠️ The **CloudFront
> certificate MUST be in `us-east-1`** (CloudFront only reads ACM from there). The
> ALB certificate is separate and lives in `ap-south-1`. So you'll request the
> wildcard cert **twice** (once per region).

> **Domain:** `pragmatic-dev.in` (registered **and DNS-hosted at GoDaddy**).
> **Subdomains:** `app.pragmatic-dev.in` (frontend/CloudFront),
> `api.pragmatic-dev.in` (backend/ALB), apex → redirects to `app`.

> ✅ **Domain verified (2026-07-08):** hosting resumed. **DNS stays on GoDaddy**
> (no Route 53 hosted zone) to keep **$0 DNS cost on the free tier**. Everywhere
> this runbook used to say "create a record in Route 53," you instead **add a
> record in the GoDaddy DNS manager**: `app` and `api` as **CNAMEs**, the apex via
> **GoDaddy Forwarding**, and the ACM validation records as **CNAMEs in GoDaddy**.

---

## Phase 0 — Account, security & cost guardrails

1. **Create the AWS account** (root email + strong password).
2. **Secure the root user:** enable **MFA** on root; then **stop using root** for
   daily work.
3. **Create an admin identity for daily use** — either:
   - **IAM Identity Center (SSO)** user (recommended), or
   - an **IAM user** in the `Administrators` group, with **MFA**.
4. **Set a budget alarm (do this first — you're cost-sensitive):**
   AWS **Budgets** → monthly cost budget (e.g. **$10**) → email alert at 50/80/100%.
5. **Install & configure the AWS CLI:**
   ```powershell
   aws configure   # access key, secret, default region = ap-south-1, output = json
   aws sts get-caller-identity   # verify it works
   ```

**Cost:** $0 (budgets and IAM are free).

---

## Phase 1 — DNS: keep it on GoDaddy (no Route 53)

We host DNS **on GoDaddy** to stay at **$0** on the free tier. There's no hosted
zone to create — you just add records in the GoDaddy DNS manager as each AWS
target becomes available (CloudFront domain in Phase 4, ALB DNS in Phase 7).

1. **Confirm GoDaddy is authoritative:** GoDaddy → your domain → **Nameservers**
   should show GoDaddy's default nameservers (don't delegate away). Verify:
   ```powershell
   nslookup -type=NS pragmatic-dev.in
   ```
   It should return GoDaddy nameservers.
2. **Records you'll add later** (kept here for reference):
   - **CNAME** `app` → CloudFront domain `d<xxxx>.cloudfront.net` *(Phase 4)*
   - **CNAME** `api` → ALB DNS `<alb>.ap-south-1.elb.amazonaws.com` *(Phase 7h)*
   - **CNAME** `_<acm-token>` → ACM validation target *(Phase 2)*
   - **Apex forwarding** `pragmatic-dev.in` → `https://app.pragmatic-dev.in`
     (GoDaddy → **Domain → Forwarding**, 301, forward with masking off).
3. **Apex caveat:** DNS forbids a CNAME at the zone apex and GoDaddy has no
   ALIAS/ANAME, so the bare domain uses **GoDaddy Forwarding** (not a DNS record)
   to redirect to `app.`.

**Cost:** **$0** — DNS stays on GoDaddy; no Route 53 hosted zone.

---

## Phase 2 — TLS certificates (ACM)

Request a **wildcard** cert `*.pragmatic-dev.in` **and** apex `pragmatic-dev.in`.

### 2a. CloudFront cert — in `us-east-1`
1. ACM (**N. Virginia / us-east-1**) → Request public certificate.
2. Domains: `pragmatic-dev.in` and `*.pragmatic-dev.in`.
3. Validation: **DNS**. ACM shows a **CNAME name/value** for validation → copy it
   and **add it as a CNAME in the GoDaddy DNS manager** (there's no "Create records
   in Route 53" button since DNS is on GoDaddy). Tip: GoDaddy appends the domain
   automatically, so paste only the **host portion** of the CNAME name (strip the
   trailing `.pragmatic-dev.in`). Wait until status = **Issued**.

### 2b. ALB cert — in `ap-south-1`
Repeat the exact same request in **ap-south-1** (ALB reads its region's ACM).
Same domains, same DNS validation. Both regions issue the **same CNAME validation
record**, so the GoDaddy record you added in 2a validates this one too.

**Cost:** ACM public certs are **free**.

---

## Phase 3 — S3 bucket (frontend static hosting)

1. **Create bucket** (e.g. `pragmatic-dev-frontend`) in **ap-south-1**.
2. **Block ALL public access = ON** (keep it private — CloudFront reads it via
   OAC, below). No static website hosting needed.
3. *(Optional)* enable Versioning for easy rollback.

**Cost:** a few cents/month for a few MB.

---

## Phase 4 — CloudFront distribution (the CDN)

1. **Create distribution**, Origin = your S3 bucket.
2. **Origin access:** create/use an **Origin Access Control (OAC)**. CloudFront
   will show a **bucket policy** to paste into the S3 bucket (grants only this
   distribution read access). Apply it.
3. **Viewer protocol policy:** Redirect HTTP → HTTPS.
4. **Default root object:** `index.html`.
5. **Alternate domain name (CNAME):** `app.pragmatic-dev.in`.
6. **Custom SSL certificate:** the **us-east-1** wildcard cert from Phase 2a.
7. **SPA routing — custom error responses:** map both **403** and **404** →
   response page `/index.html`, **HTTP 200**. (single-spa serves one HTML for all
   client routes.)
8. **Cache:** use the managed **CachingOptimized** policy for hashed JS/CSS. The
   deploy script (Phase 6-frontend) sets `index.html` to `no-cache` so new
   releases show immediately.
9. Note the distribution domain: **`d<xxxx>.cloudfront.net`**.
10. **GoDaddy DNS:** add a **CNAME** record `app` → `d<xxxx>.cloudfront.net`.
    (GoDaddy can't alias the apex, so the bare domain uses **Forwarding** →
    `https://app.pragmatic-dev.in`, set under Domain → Forwarding.)

**Cost:** effectively free at your traffic (generous free tier + pennies after).

---

## Phase 5 — 🔬 LOCAL TEST CHECKPOINT (baseapp → CDN bundles)

Goal: after pushing the webpack build to S3, confirm the **baseapp loads the MFE
bundles from the CloudFront URL** — tested locally before any backend move.

1. **Build & upload the MFE bundles** to S3 (manual first pass):
   ```powershell
   cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\tipsapp;  npm run build
   cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\queryapp; npm run build
   cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\baseapp;  npm run build
   aws s3 sync .\frontend\tipsapp\dist  s3://pragmatic-dev-frontend/ --exclude "*.map"
   aws s3 sync .\frontend\queryapp\dist s3://pragmatic-dev-frontend/ --exclude "*.map"
   aws s3 sync .\frontend\baseapp\dist  s3://pragmatic-dev-frontend/ --exclude "*.map"
   ```
2. **Point the baseapp import-map at the CDN** and run it locally. Two ways:
   - **Quick:** use the built-in **import-map-overrides** widget (already in
     `index.ejs`) to repoint `@pragmatic-dev/tipsapp` / `queryapp` →
     `https://d<xxxx>.cloudfront.net/pragmatic-dev-tipsapp.js`, or
   - **Proper:** rebuild baseapp with a `CDN_BASE` pointing at the CloudFront URL
     (this comes from the Phase-1 code change in `deployment-plan.md`).
3. **Verify in the browser** (`http://localhost:9000`): Network tab shows the
   tips/query bundles loading from `d<xxxx>.cloudfront.net` with HTTP 200, and the
   app renders. API calls still hit your **local backend** (`localhost:8000`).

✅ Passing this checkpoint means the CDN path works before we touch ECS.

---

## Phase 6 (frontend) — Deploy script + cache headers

Automate the build → sync → invalidate cycle:
- Build all three apps (production).
- ⚠️ **Our MFE bundles have FIXED filenames** (`pragmatic-dev-tipsapp.js`,
  `pragmatic-dev-queryapp.js`, `pragmatic-dev-root-config.js`) because the SystemJS
  import-map references those exact URLs. They are **not** content-hashed, so the
  "immutable, max-age=1yr" trick does **NOT** apply — a same-named bundle would be
  served stale for a year.
- `aws s3 sync` with correct **content-types** and `Cache-Control: no-cache` on **all**
  files (JS + `index.html`). `no-cache` = still cached but revalidated via ETag (cheap 304s).
- **Invalidate everything** on CloudFront so releases appear immediately (only ~4 files,
  and a `/*` wildcard counts as 1 path against the free 1,000/month):
  ```powershell
  aws cloudfront create-invalidation --distribution-id E1OHD40X5ASPPS --paths "/*"
  ```
- **Future (Option B):** add `[contenthash]` to bundle filenames + generate the import-map
  at build time → then hashed assets can use `public,max-age=31536000,immutable`.
*(I can generate `scripts/deploy-frontend.ps1` for this.)*

---

## Phase 7 — Backend on ECS (ECR → Redis → network → ECS → ALB)

### 7a. ECR — container registry
```powershell
aws ecr create-repository --repository-name pragmatic-dev/backend
aws ecr create-repository --repository-name pragmatic-dev/worker
# authenticate docker, then build & push each image (backend, worker)
```

### 7b. Secrets (don't bake keys into images)
Store `OPENAI_API_KEY` in **SSM Parameter Store (SecureString)** or **Secrets
Manager**; the task definition injects it as an env var at runtime.
- SSM Parameter Store: **free** for standard params (prefer this for cost).

### 7c. ElastiCache — Redis
1. Create **ElastiCache for Redis**, node **`cache.t4g.micro`**, single node.
2. Put it in the same VPC; create a **subnet group** across 2 AZs.
3. **Security group:** allow inbound **6379** from the ECS task security group.
4. Note the **primary endpoint** → becomes `REDIS_HOST` for backend + worker.

**Cost:** ~**$11–12/month** (single `t4g.micro`).

### 7d. Networking (VPC) — keep it cheap
- Use the **default VPC** (2 public subnets) to start.
- **Avoid a NAT Gateway** (~$32/mo!). Instead run Fargate tasks in **public
  subnets with a public IP** so they can reach the internet (ECR pull, OpenAI).
- Security groups:
  - **ALB SG:** inbound 443 (and 80→443 redirect) from `0.0.0.0/0`.
  - **Task SG:** inbound 8000 from the **ALB SG** only.
  - **Redis SG:** inbound 6379 from the **Task SG** only.

### 7e. ECS cluster + task definitions (Fargate)
1. Create an **ECS cluster** (Fargate).
2. **backend task def:** image from ECR, port **8000**, env
   (`REDIS_HOST`=ElastiCache endpoint, `CORS_ORIGINS=https://app.pragmatic-dev.in`,
   `OPENAI_API_KEY` from SSM). Size **0.5 vCPU / 1 GB**.
3. **worker task def:** same image family (worker), command
   `celery -A worker.celery_app worker --beat --pool=threads --concurrency=2`
   (embedded Beat OK on Linux). Size **0.25 vCPU / 0.5 GB**. Consider **Fargate
   Spot** for this one.

### 7f. ALB + HTTPS
1. Create an **Application Load Balancer** (internet-facing, public subnets).
2. **Target group** → backend tasks, port 8000, health check path **`/health`**.
3. **Listener 443** with the **ap-south-1** wildcard cert; **listener 80**
   redirects to 443.

### 7g. ECS services
1. **backend service** → attach to the ALB target group, desired count **1**.
2. **worker service** → no load balancer, desired count **1**.

### 7h. DNS for the API
**GoDaddy DNS** → add a **CNAME** record `api` → the **ALB DNS name**
(`<alb>.ap-south-1.elb.amazonaws.com`). (ALB has no static IP, so CNAME — not an
A record — is correct here.)

### 7i. Point the frontend at the API + redeploy
Set the prod MFE API base to `https://api.pragmatic-dev.in` (via the shell’s
`window.__TIPS_API_BASE__` / `__QUERY_API_BASE__` at build), re-sync to S3, and
invalidate `index.html`.

---

## Phase 8 — Cost controls (single-user demo)

- **Budget alarm** from Phase 0 (most important).
- **Scale ECS to 0** when idle: `aws ecs update-service --desired-count 0` for
  backend + worker; scale to 1 before a demo. (A tiny script can toggle both.)
- **Fargate Spot** for the worker (and optionally backend outside demos).
- **ElastiCache** is the main always-on cost (~$12/mo). To zero it out between
  long idle periods, delete the node (recreate when needed) or run Redis as a
  container in the worker task during early development.
- Frontend (S3+CloudFront) and DNS/ACM are effectively free.

**Rough monthly cost:** ~**$12–20** with scale-to-zero + Spot; ~**$35–50** if
everything runs 24/7.

---

## Order-of-operations checklist

- [ ] Phase 0: account, MFA, budget, CLI
- [ ] Phase 1: GoDaddy DNS confirmed (no Route 53); records added as targets appear
- [ ] Phase 2: ACM wildcard cert in **us-east-1** *and* **ap-south-1** (validate via GoDaddy CNAME)
- [x] Phase 3: private S3 bucket — `pragmatic-dev-frontend-498341975274-ap-south-1-an`
- [x] Phase 2a: ACM cert **Issued** in us-east-1 (`pragmatic-dev.in` + `*.pragmatic-dev.in`),
  DNS-validated via GoDaddy CNAME `_a4f346e429c105d32cd05e4e82e5a857`.
- [x] Phase 4: CloudFront **complete** — dist `E1OHD40X5ASPPS`,
  domain `d20ykt0v2zz3g.cloudfront.net`, OAC `EZALQMNGYSLF6`, bucket policy applied,
  root object `index.html`, SPA 403/404→`/index.html`, Price Class 200.
  **Custom domain live:** `https://app.pragmatic-dev.in` (alt-domain + us-east-1 cert +
  GoDaddy `app` CNAME → CloudFront), HTTPS verified (edge MAA51/Chennai).
  **Apex forwarding live:** `http://pragmatic-dev.in` → 301 → `https://app.pragmatic-dev.in`
  (GoDaddy Forwarding, Permanent 301, Forward only). Direct `https://pragmatic-dev.in`
  (port 443) may lag while GoDaddy provisions the apex TLS listener — resolves on its own.
- [x] **Phase 5: live CDN test passed** — `https://d20ykt0v2zz3g.cloudfront.net` loads,
  both MFEs mount, bundles served from CDN, deep-link SPA fallback works.
- [x] Phase 6: frontend deploy script — `scripts/deploy-frontend.ps1` (build → S3 sync
  with cache headers → CloudFront `/*` invalidation; `-DryRun`, `-SkipBuild`, `-BundleMaxAge`).
- [ ] Phase 7: ECR, secrets, ElastiCache, VPC/SGs, ECS, ALB + GoDaddy `api` CNAME
- [ ] Phase 8: budget + scale-to-zero + Spot

