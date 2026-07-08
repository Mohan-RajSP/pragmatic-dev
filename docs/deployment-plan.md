# Deployment Plan — Pragmatic-dev

Living document for taking the app to AWS. Captures **decisions made** and
**open items**. Companion to [`local-commands.md`](./local-commands.md).

> Status: **planning**. Nothing here is executed yet — it's the agreed blueprint.
>
> ✅ **Domain verified (2026-07-08):** `pragmatic-dev.in` registration is cleared,
> so hosting can resume. **DNS decision locked in — we stay on GoDaddy DNS**
> (Option A) to keep cost at **$0** on the AWS **free tier** (no Route 53 hosted
> zone). CloudFront and ALB are reached via **CNAME records added in GoDaddy**;
> the apex uses **GoDaddy domain forwarding**.

---

## 1. Target architecture

```
                         ┌────────────────────────────┐
  app.pragmatic-dev.in ─►│  CloudFront (CDN, global)  │─► S3 (private, static)
                         └────────────────────────────┘     index.html
                                                            *-root-config.js
                                                            *-tipsapp.js
                                                            *-queryapp.js

  api.pragmatic-dev.in ─► ALB ─► ECS Fargate (backend FastAPI)
                                   + worker (Celery + embedded Beat)
                                 ElastiCache (Redis)
```

- **Frontend (shell + both MFEs) → S3 + CloudFront** (static). Removes all 3
  frontend containers from ECS.
- **Backend → ECS Fargate** behind an ALB, reached at `api.pragmatic-dev.in`.
- **Redis → ElastiCache** (`cache.t4g.micro`).

---

## 2. Domain & DNS  ✅ verified · ✅ decided (GoDaddy DNS)

Registered **and DNS-hosted at GoDaddy**: `pragmatic-dev.in` (verification cleared
2026-07-08).

> ✅ **Decision:** stay on **GoDaddy DNS (Option A)** — no Route 53 hosted zone, so
> **$0 DNS cost** on the free tier. We add the CloudFront and ALB targets as
> **CNAME records directly in the GoDaddy DNS manager**; the apex is handled with
> **GoDaddy domain forwarding** (DNS forbids a CNAME at the zone apex, and GoDaddy
> has no ALIAS/ANAME).

| Name | Purpose | GoDaddy record | Points to |
|------|---------|----------------|-----------|
| `app.pragmatic-dev.in` | Frontend SPA | **CNAME** | CloudFront distribution (`d<xxxx>.cloudfront.net`) |
| `api.pragmatic-dev.in` | Backend API | **CNAME** | ALB DNS name (`<alb>.ap-south-1.elb.amazonaws.com`) |
| `pragmatic-dev.in` (apex) | Redirect | **Forwarding** | → `https://app.pragmatic-dev.in` (301) |

**TLS:** one **wildcard ACM cert `*.pragmatic-dev.in`** issued in **us-east-1**
(required by CloudFront); covers `app`, `api`, and future subdomains. Because DNS
lives on GoDaddy, the ACM **DNS-validation CNAME records are added manually in
GoDaddy** (there's no "Create records in Route 53" shortcut).

### DNS options (apex can't be a CNAME) — decided: **A**
- **A) ✅ Chosen — Stay on GoDaddy (free):** `app`/`api` as **CNAME** records → their
  AWS targets; apex uses **GoDaddy Forwarding** → `https://app.pragmatic-dev.in`.
- **B) Not used — Move DNS to Cloudflare (free) or Route 53 (~$0.50/mo):** supports
  **apex alias/flattening**, so the bare domain can point straight at CloudFront
  with no forwarding hop. Rejected for now to avoid Route 53 cost on the free tier.

> Reasoning: the DNS spec forbids a CNAME at the zone apex; GoDaddy has no
> ALIAS/ANAME support, hence the forwarding hop in option A.

---

## 3. CORS note (consequence of the app/api split)

`app.pragmatic-dev.in` → `api.pragmatic-dev.in` is **cross-origin**.
- **Implemented:** the backend now uses an **explicit allow-list** (not `*`),
  because `allow_credentials=True` is incompatible with a wildcard origin. It
  includes local dev origins + `https://app.pragmatic-dev.in`
  (`backend/app/core/config.py`, overridable via `CORS_ORIGINS`).
- **In production:** set `CORS_ORIGINS=https://app.pragmatic-dev.in` (drop the
  localhost entries) — no code change needed.
- **When auth/cookies arrive:** keep it locked to `https://app.pragmatic-dev.in`
  with credentials enabled.

> Full AWS runbook: [`aws-deployment-runbook.md`](./aws-deployment-runbook.md).

---

## 4. Frontend → CDN: phased steps

| Phase | What | Output |
|-------|------|--------|
| 0 | Confirm decisions + verify AWS CLI access | — |
| 1 | Make import-map + API base **env-aware** (webpack `templateParameters` + `index.ejs`); prod injects CDN base + `api.pragmatic-dev.in` | code change |
| 2 | Production build of all 3 apps (`CDN_BASE`, `API_BASE`) | `dist/` folders |
| 3 | Provision **S3** (private, Block Public Access) + **CloudFront** (OAC, `index.html` root, SPA 403/404 → index.html) | AWS resources |
| 4 | **Deploy script** (`scripts/deploy-frontend.ps1`): build → `aws s3 sync` (content-types + cache headers) → CloudFront invalidation | script |
| 5 | Point import-map at CloudFront/`app.pragmatic-dev.in`, redeploy, verify | working CDN |
| 6 | *(later)* Attach custom domain + wildcard cert; DNS per §2 | custom domain |

---

## 5. Prerequisites

1. AWS account + IAM user/role with **S3 + CloudFront** perms (ECR/ECS later).
2. **AWS CLI** installed & configured (`aws configure`).
3. Node/npm (already present) to build bundles.
4. A **globally-unique S3 bucket name** (proposed: `pragmatic-dev-frontend`).
5. *(Phase 6)* wildcard ACM cert in **us-east-1** + **GoDaddy DNS access** (to add
   the ACM validation CNAMEs and the `app.`/`api.` CNAME records).

---

## 6. Open decisions

- ✅ **Domain verification** — cleared 2026-07-08; custom-domain hosting can resume.
- ✅ **DNS provider** — **GoDaddy DNS** (Option A), no Route 53 (free-tier $0 DNS).
- **AWS region** for S3 + ECS (e.g. `ap-south-1` Mumbai vs `us-east-1`).
- **Bucket name** (propose `pragmatic-dev-frontend`).
- **When to attach the custom domain** — start on default `*.cloudfront.net`,
  add `app.pragmatic-dev.in` in Phase 6? (recommended)

---

## 7. Cost (single-user learning app)

- **S3 + CloudFront:** effectively free (few MB, minimal traffic).
- **ACM cert:** free.
- **DNS:** **$0** — hosted on **GoDaddy** (Option A), no Route 53 hosted zone.
- **Backend (later):** lean ECS (~1.25 vCPU / 2.5 GB) + ElastiCache `t4g.micro`;
  scale-to-zero between sessions to minimize cost.


