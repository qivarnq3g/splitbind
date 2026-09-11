# Recipient Email Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change. Do not modify production code before a failing test exists.

**Goal:** Thay UX "Mã người nhận" bằng "Email người nhận" bắt buộc và "Họ và tên" tùy chọn, trong khi vẫn giữ `recipient_id` là định danh UUID nội bộ dùng bởi Issuance, Manifest và các cơ chế truy vết.

**Architecture:** Người dùng chỉ cung cấp email và có thể cung cấp họ tên. Backend chịu trách nhiệm tìm Recipient hiện có trong cùng tổ chức hoặc tạo Recipient mới, sau đó lấy `recipient_id` nội bộ để tiếp tục toàn bộ issuance flow hiện tại. Không thay đổi thuật toán watermark, Signed Manifest, SHA-256, Ed25519, verification semantics hoặc benchmark.

**Tech Stack:** React + TypeScript + Vite ở `apps/web`; Django + PostgreSQL ở `services/api`; pytest cho backend; test runner hiện hữu của `@splitbind/web` cho frontend.

**Spec:** Chính tài liệu này, mục "Design Contract".

## 0. Design Contract

### 0.1. UX phải đạt

Trang `/issue` phải có đúng ý nghĩa sau:

```text
Tệp PDF
[ Chọn tệp ]

Email người nhận *
[ nguyenvana@example.com ]

Họ và tên
[ Nguyễn Văn A ]
Không bắt buộc

[ Tạo bản cấp phát ]
```

Người dùng không phải biết, nhìn thấy, copy hoặc paste UUID `recipient_id`.

### 0.2. Hành vi backend phải đạt

Khi người dùng gửi:

```text
recipient_email = " NguyenVanA@Example.com "
recipient_name  = " Nguyễn Văn A "
```

backend phải:

1. Trim khoảng trắng đầu cuối của email.
2. Validate email.
3. Tìm Recipient trong đúng organization hiện tại bằng so khớp email không phân biệt hoa thường.
4. Nếu đã tồn tại, dùng lại cùng `recipient_id`.
5. Nếu chưa tồn tại, tạo Recipient mới và sinh `recipient_id`.
6. Nếu `recipient_name` rỗng, vẫn cho phép cấp phát.
7. Nếu Recipient cũ chưa có tên và request mới có tên, cho phép điền tên còn thiếu.
8. Nếu Recipient cũ đã có tên, không tự động ghi đè bằng tên mới chỉ vì người dùng nhập khác.
9. Tạo Issuance bằng `recipient_id` nội bộ vừa resolve.
10. Signed Manifest vẫn ghi `recipient_id` như hiện tại.
11. Không đưa email vào Manifest nếu kiến trúc hiện tại không có yêu cầu đó.
12. Không dùng email như bằng chứng xác minh danh tính hay ownership của hộp thư.

### 0.3. Tương thích ngược

Để giảm regression, backend nên giữ đường cũ nhận `recipient_id` trong thời gian hiện tại nếu endpoint đang được test hoặc dùng ở nơi khác.

Quy tắc:

```text
recipient_email có giá trị, recipient_id trống  -> new UX path
recipient_id có giá trị, recipient_email trống  -> legacy path
cả hai cùng có giá trị                          -> 400 validation error
cả hai cùng trống                               -> 400 validation error
```

Frontend production mới chỉ dùng `recipient_email` và `recipient_name`.

### 0.4. Non-goals

Không làm các việc sau trong task này:

- Không sửa thuật toán watermark.
- Không sửa semi-fragile tamper localization.
- Không sửa SHA-256, Ed25519, RFC 8785 JCS hoặc Signed Manifest semantics.
- Không đổi `issuance_id`.
- Không đổi `recipient_id` trong database thành email.
- Không xóa `recipient_id`.
- Không xây trang quản lý Recipient đầy đủ.
- Không thêm gửi email thật.
- Không thêm xác minh OTP.
- Không thêm invitation flow.
- Không redesign toàn bộ frontend.
- Không đổi production copy ở trang Verify nếu không bị task này tác động.
- Không sửa knowledge base học thuật chỉ vì thay UX.

## 1. Preflight bắt buộc trước khi sửa

### Task 1: Xác định đúng worktree, branch và flow hiện tại

**Known frontend file từ lịch sử project:**

- `apps/web/src/pages/IssueDocumentPage.tsx`

**Backend file chính xác chưa được cung cấp trong tài liệu bàn giao. Agent phải tìm bằng code search, không được đoán tên.**

- [ ] **Step 1: Đọc instruction của repository**

Từ repository root, tìm và đọc toàn bộ các file instruction áp dụng:

```powershell
Get-ChildItem -Path . -Filter AGENTS.md -Recurse
Get-ChildItem -Path . -Filter CLAUDE.md -Recurse
Get-ChildItem -Path . -Filter GEMINI.md -Recurse
```

Nếu có instruction ở root và trong subdirectory, áp dụng instruction gần file nhất.

- [ ] **Step 2: Xác nhận đang ở đúng worktree**

```powershell
Get-Location
git status -sb
git branch
git log -5
```

Không sửa code nếu đang đứng nhầm repository hoặc worktree.

Ưu tiên worktree SplitBind đang chứa `apps/web` và `services/api`.

- [ ] **Step 3: Kiểm tra working tree**

```powershell
git status -sb
git diff
```

Nếu có thay đổi chưa commit không liên quan task này, không ghi đè chúng. Báo rõ trước khi tiếp tục nếu có nguy cơ conflict.

- [ ] **Step 4: Xác định frontend source của "Mã người nhận"**

```powershell
rg -n "Mã người nhận|recipient_id|recipientId|recipient" apps/web/src
```

Agent phải ghi lại:

```text
Issue page file:
Form state field:
Submit function:
API client function:
Frontend tests liên quan:
```

Known evidence cho thấy `IssueDocumentPage.tsx` tồn tại. Tuy nhiên vẫn phải đọc file thật trước khi sửa.

- [ ] **Step 5: Xác định backend issuance endpoint**

```powershell
rg -n "recipient_id|recipientId" services/api
rg -n "Issuance|issue|issuance" services/api/splitbind services/api/tests
```

Agent phải tìm ra chính xác:

```text
HTTP endpoint:
Request schema / serializer:
Handler / view:
Issuance creation service:
Recipient model nếu có:
Database field lưu recipient_id:
Backend tests hiện tại:
OpenAPI schema source:
```

- [ ] **Step 6: Xác định Recipient entity có thực sự tồn tại không**

```powershell
rg -n "class Recipient|Recipient\(" services/api
rg -n "email.*models\.|EmailField|full_name|display_name|recipient_name" services/api
```

### Hard gate sau Task 1

Chỉ tiếp tục plan nếu repo đã có một Recipient entity hoặc một cấu trúc dữ liệu tương đương có thể lưu email cho một `recipient_id`.

Nếu **không có Recipient entity và database hiện chỉ lưu UUID thô trên Issuance**, task không còn là bounded UX change. Dừng lại và báo:

```text
ARCHITECTURE GAP:
Current repository has no Recipient entity that can map email -> recipient_id.
Do not implement an ad-hoc email field on Issuance.
Need an architectural decision before proceeding.
```

Không tự ý tạo subsystem quản lý Recipient khi chưa được duyệt.

## 2. Khóa contract API trước khi code

### Task 2: Viết contract behavior bằng test backend

**Files:**

- Modify: request schema / serializer được tìm thấy ở Task 1
- Modify: issuance handler/service được tìm thấy ở Task 1
- Test: file test issuance endpoint hiện hữu được tìm thấy ở Task 1

**Interfaces mới ở HTTP layer:**

```text
recipient_email: string, required cho new UX path
recipient_name: string, optional
recipient_id: UUID, optional legacy input
```

**Internal output bắt buộc:**

```text
resolved_recipient_id: UUID
```

Sau bước resolve, phần issuance hiện hữu chỉ nên nhận `resolved_recipient_id` và chạy như trước.

- [ ] **Step 1: Viết failing test cho email mới**

Copy setup/fixture từ test issuance hiện hữu. Test phải:

```python
# Pseudocode, đổi tên fixture theo codebase thật.
response = authenticated_client.post(
    ISSUE_ENDPOINT,
    data={
        "file": valid_pdf,
        "recipient_email": "new.person@example.com",
        "recipient_name": "",
    },
)
assert response.status_code in (200, 201, 202)

recipient = Recipient.objects.get(
    organization=current_organization,
    email__iexact="new.person@example.com",
)
issuance = Issuance.objects.get(pk=extract_issuance_id(response))
assert issuance.recipient_id == recipient.pk
```

Không copy tên fixture giả vào production code. Hãy dùng fixture thật của repository.

- [ ] **Step 2: Chạy riêng test và xác nhận RED**

Dùng command pytest đúng file test vừa thêm:

```powershell
python -m pytest PATH_TO_REAL_TEST_FILE -q
```

Phải FAIL vì endpoint chưa nhận `recipient_email`, không phải vì typo hay fixture hỏng.

- [ ] **Step 3: Viết failing test cho email đã tồn tại**

Case:

```text
Recipient đã có:
email = "student@example.com"

Request:
recipient_email = " STUDENT@example.com "
```

Assert:

```text
không tạo Recipient thứ hai
Issuance mới dùng đúng recipient_id cũ
```

- [ ] **Step 4: Viết failing test cho tên tùy chọn**

Hai case:

```text
A. recipient_name trống -> request vẫn thành công
B. Recipient cũ có full_name trống + request có tên -> tên được bổ sung
```

- [ ] **Step 5: Viết failing test không ghi đè tên đã có**

Case:

```text
DB:
email = "student@example.com"
name  = "Nguyễn Văn A"

Request:
email = "student@example.com"
name  = "Tên khác"
```

Expected:

```text
Recipient vẫn là "Nguyễn Văn A"
Issuance vẫn được tạo
```

Task này không phải trang chỉnh sửa danh bạ.

- [ ] **Step 6: Viết failing test invalid email**

Các input tối thiểu:

```text
""
"abc"
"abc@"
"@example.com"
```

Expected:

```text
HTTP 400
field error gắn với recipient_email
không tạo Recipient
không tạo Issuance
```

- [ ] **Step 7: Viết failing test conflict giữa email và legacy id**

Request có cả:

```text
recipient_email
recipient_id
```

Expected HTTP 400 với message dễ hiểu.

- [ ] **Step 8: Viết failing test thiếu cả hai**

Không có `recipient_email`, không có `recipient_id`.

Expected HTTP 400.

- [ ] **Step 9: Viết failing test organization isolation**

Nếu Recipient model scoped theo organization:

```text
Org A có student@example.com
Org B issue cho student@example.com
```

Expected:

```text
Org B không reuse recipient_id của Org A
```

Nếu model không scoped theo organization, ghi rõ evidence và không tự thêm organization relation trong task bounded này.

- [ ] **Step 10: Viết failing test Manifest giữ recipient_id**

Sau issuance bằng email:

```python
assert signed_manifest["recipient_id"] == str(resolved_recipient.pk)
```

Tên key phải lấy từ Manifest contract hiện hữu.

Không thêm `recipient_email` hoặc `recipient_name` vào signed Manifest trong task này.

## 3. Backend implementation tối thiểu

### Task 3: Thêm recipient resolver

**Responsibility:** Chuyển input thân thiện với user thành Recipient nội bộ.

Ưu tiên tạo helper/service nhỏ cạnh issuance service hiện hữu. Không nhét toàn bộ logic vào HTTP view nếu project đã có service layer.

**Reference algorithm:**

```python
def resolve_recipient_for_issue(
    *,
    organization,
    recipient_email: str,
    recipient_name: str | None,
):
    email = recipient_email.strip()
    validate_email(email)

    name = (recipient_name or "").strip()

    recipient = (
        Recipient.objects
        .filter(
            organization=organization,
            email__iexact=email,
        )
        .first()
    )

    if recipient is not None:
        if name and not recipient.full_name.strip():
            recipient.full_name = name
            recipient.save(update_fields=["full_name"])
        return recipient

    return Recipient.objects.create(
        organization=organization,
        email=email,
        full_name=name,
    )
```

Đây là thuật toán hành vi, không phải code copy-paste bắt buộc. Agent phải ánh xạ:

```text
organization
email
full_name
Recipient
```

sang field thật đã xác minh ở Task 1.

### Quy tắc email

Không tự phát minh email canonicalization phức tạp.

Trong scope này:

```text
Storage:
trim đầu cuối

Lookup:
case-insensitive trong cùng organization

Validation:
dùng validator / field validation hiện hữu của Django
```

Không dùng email làm security identity.

### Concurrency và uniqueness

- Nếu database đã có unique constraint phù hợp, dùng nó.
- Nếu database chưa có uniqueness và codebase có nguy cơ tạo duplicate Recipient khi hai request đồng thời, ghi nhận risk.
- Không tự thêm migration functional unique constraint nếu schema ownership chưa rõ.

Nếu task cần constraint mới để correctness, dừng và báo rằng thay đổi đã nâng cấp từ bounded lên schema change cần review.

Django hỗ trợ functional `UniqueConstraint`, ví dụ constraint trên `Lower(field)`, nhưng chỉ dùng khi đã quyết định migration là cần thiết.

- [ ] **Step 1: Implement validation contract tối thiểu**

Request schema phải chấp nhận:

```text
recipient_email
recipient_name
recipient_id legacy
```

và enforce exclusive input rule.

- [ ] **Step 2: Implement resolver**

Dùng transaction pattern hiện có của project.

- [ ] **Step 3: Kết nối resolver vào issuance flow**

Flow phải thành:

```text
HTTP request
-> validate recipient input
-> resolve Recipient
-> resolved recipient_id
-> existing issuance flow
-> existing Manifest flow
-> existing storage/job flow
```

Không duplicate issuance logic.

- [ ] **Step 4: Chạy test mới**

```powershell
python -m pytest PATH_TO_REAL_TEST_FILE -q
```

Expected: tất cả test mới PASS.

- [ ] **Step 5: Chạy test backend issuance/release hiện hữu liên quan**

Từ lịch sử project, các suite quan trọng nằm trong:

```text
services/api/tests/release
services/api/tests/demo
services/api/tests/openapi/test_schema.py
services/api/tests/jobs/test_api.py
```

Chạy suite hẹp trước, sau đó suite rộng đã được project dùng trước đây.

```powershell
python -m pytest services/api/tests/release services/api/tests/demo services/api/tests/openapi/test_schema.py services/api/tests/jobs/test_api.py -q
```

Không tuyên bố "backend pass" nếu chỉ chạy một test file.

## 4. Frontend TDD

### Task 4: Thay "Mã người nhận" bằng email + tên tùy chọn

**Files known:**

- Modify: `apps/web/src/pages/IssueDocumentPage.tsx`
- Có thể modify: API client/type file được tìm thấy ở Task 1
- Test: test file hiện hữu của issue flow được tìm thấy bằng `rg`

- [ ] **Step 1: Tìm test hiện hữu**

```powershell
rg -n "IssueDocumentPage|Tạo bản cấp phát|Mã người nhận|recipient_id" apps/web/src apps/web
```

- [ ] **Step 2: Viết failing test UI copy**

Test phải assert:

```text
Có label "Email người nhận"
Có input type=email hoặc semantics tương đương
Có label "Họ và tên"
Có text "Không bắt buộc" hoặc equivalent
Không còn label "Mã người nhận"
Không còn placeholder "Dán mã người nhận được cấp"
```

- [ ] **Step 3: Chạy test và xác nhận RED**

Dùng command test hiện hữu của workspace với file test thật.

Ví dụ nếu runner hỗ trợ path trực tiếp:

```powershell
npm test -w @splitbind/web PATH_TO_REAL_FRONTEND_TEST
```

Nếu project dùng command khác, lấy command từ `apps/web/package.json`. Không đoán.

- [ ] **Step 4: Viết failing test submit payload**

Khi user nhập:

```text
email = student@example.com
name  = Nguyễn Văn A
```

API client phải nhận:

```json
{
  "recipient_email": "student@example.com",
  "recipient_name": "Nguyễn Văn A"
}
```

Frontend mới không được gửi `recipient_id`.

- [ ] **Step 5: Viết failing test email-only**

Input:

```text
student@example.com
```

Name blank.

Expected submit vẫn được gọi.

- [ ] **Step 6: Viết failing test invalid email**

Ví dụ `abc`.

Expected:

```text
không submit
hiển thị lỗi gần field email
```

Nếu validation chính của app hiện đặt ở backend, frontend vẫn nên tận dụng `type="email"` và render backend field error.

- [ ] **Step 7: Implement minimal form state**

State conceptual:

```ts
const [recipientEmail, setRecipientEmail] = useState("")
const [recipientName, setRecipientName] = useState("")
```

Không lưu `recipient_id` trong UI state mới.

- [ ] **Step 8: Implement copy dễ hiểu**

Recommended Vietnamese copy:

```text
Email người nhận
Nhập email của người sẽ nhận bản cấp phát.

Họ và tên
Không bắt buộc. Dùng để dễ nhận biết người nhận trong hồ sơ.
```

Button vẫn:

```text
Tạo bản cấp phát
```

- [ ] **Step 9: Implement request mapping**

Nếu API đang dùng multipart form:

```text
file
recipient_email
recipient_name
```

Nếu `recipient_name` trống, gửi chuỗi rỗng hoặc omit theo contract backend đã test. Chọn một cách và test đúng cách đó.

- [ ] **Step 10: Render server validation**

Backend 400 cho `recipient_email` phải hiển thị lỗi dễ hiểu, không hiện raw JSON.

Ví dụ:

```text
Email người nhận không hợp lệ.
```

- [ ] **Step 11: Chạy frontend test file**

Expected PASS.

- [ ] **Step 12: Chạy toàn bộ web test suite và typecheck**

Dùng scripts thật trong `apps/web/package.json`.

Theo lịch sử project, workspace là `@splitbind/web`.

```powershell
npm run typecheck -w @splitbind/web
npm test -w @splitbind/web
```

Expected:

```text
typecheck exit 0
all web tests pass
```

Không chấp nhận snapshot update hàng loạt nếu chưa đọc diff.

## 5. OpenAPI và API type synchronization

### Task 5: Đồng bộ contract

- [ ] **Step 1: Kiểm tra OpenAPI schema**

```powershell
rg -n "recipient_id|recipient_email|recipient_name" services/api apps/web
```

Nếu project generate OpenAPI, dùng generator hiện hữu.

Không tự sửa generated file bằng tay nếu repository có generation script.

- [ ] **Step 2: Test schema**

```powershell
python -m pytest services/api/tests/openapi/test_schema.py -q
```

Expected PASS.

- [ ] **Step 3: Kiểm tra legacy path**

Nếu `recipient_id` được giữ backward compatible, OpenAPI phải thể hiện đúng optional/exclusive semantics trong phạm vi framework hỗ trợ.

Nếu schema framework khó biểu diễn `oneOf`, tối thiểu phải document bằng description và backend validation vẫn bắt buộc.

## 6. Data model safety review

### Task 6: Không để email phá identity model

Agent phải xác minh các invariants sau trong code và test:

```text
recipient_id vẫn là UUID/internal primary identifier
issuance_id không đổi
Manifest recipient_id không đổi semantics
recipient_email chỉ là human-friendly lookup attribute
full name chỉ là descriptive metadata
email không được dùng thay chữ ký, auth hoặc authorization
```

### Không tự động ghi đè tên

Policy:

```text
existing name blank + new nonblank name -> fill once
existing name nonblank + different new name -> preserve existing
```

Lý do: issue form không phải contact-edit form.

### Không gửi email

Task này chỉ thay recipient input UX. Không gọi SMTP, Gmail API hoặc third-party transactional email.

## 7. Regression verification toàn hệ thống

### Task 7: Full relevant test gate

Chạy theo thứ tự:

- [ ] **Step 1: Frontend typecheck**

```powershell
npm run typecheck -w @splitbind/web
```

- [ ] **Step 2: Frontend full tests**

```powershell
npm test -w @splitbind/web
```

- [ ] **Step 3: Backend relevant suites**

```powershell
python -m pytest services/api/tests/release services/api/tests/demo services/api/tests/openapi/test_schema.py services/api/tests/jobs/test_api.py -q
```

- [ ] **Step 4: Nếu repo có test riêng cho issue endpoint ngoài các suite trên, chạy thêm**

Lấy path từ Task 1.

- [ ] **Step 5: Kiểm tra diff**

```powershell
git diff
git status -sb
```

Agent phải đọc diff, không chỉ nhìn exit code.

### Diff review checklist

Không được có thay đổi ngoài scope:

```text
research/python
watermark algorithm
integrity benchmark
manifest cryptographic field semantics
verify-page evidence wording
infra
deployment topology
knowledge base academic metrics
```

Nếu có, revert phần ngoài scope trước khi tiếp tục.

## 8. Manual UX smoke test local

### Task 8: Kiểm tra như người dùng thật

Khởi động app bằng commands chính thức trong README/development docs.

Test case 1:

```text
PDF hợp lệ
Email: first.user@example.com
Họ tên: bỏ trống
```

Expected:

```text
Tạo bản cấp phát thành công
Không cần recipient UUID
```

Test case 2:

```text
PDF hợp lệ
Email: second.user@example.com
Họ tên: Nguyễn Văn B
```

Expected thành công.

Test case 3:

Dùng lại:

```text
SECOND.USER@example.com
```

Expected:

```text
reuse cùng Recipient
không tạo duplicate do casing
```

Test case 4:

```text
abc
```

Expected:

```text
validation error rõ ràng
không tạo issuance
```

Test case 5:

Sau khi cấp phát, download PDF và chạy Verify như flow hiện tại.

Expected:

```text
exact issued file vẫn verify theo semantics hiện hữu
Signed Manifest vẫn hợp lệ
recipient_id vẫn có trong record/manifest
```

## 9. Production deployment safety

### Task 9: Chỉ deploy sau khi local gates pass

Không deploy nếu:

```text
web test fail
typecheck fail
backend relevant tests fail
OpenAPI test fail
manual issue flow fail
```

### Trước deploy

Ghi lại:

```powershell
git rev-parse HEAD
git status -sb
```

Tạo commit nhỏ, ví dụ:

```powershell
git add apps/web services/api
git commit -m "feat(issue): resolve recipients by email"
```

Nếu có migration đã được review thì add migration tương ứng. Nếu không cần migration, không tạo migration giả.

### Deploy

Dùng đúng deployment procedure đang tồn tại trong repository. Không phát minh script mới.

Sau deploy, kiểm tra tối thiểu:

```text
https://splitbind.qivarn.id.vn/issue
```

và health endpoint hiện hữu.

## 10. Production smoke test

### Task 10: Verify feature thật trên site

Test bằng một email test không chứa thông tin cá nhân thật, ví dụ:

```text
demo.recipient@example.com
```

Các bước:

1. Login admin.
2. Mở `/issue`.
3. Xác nhận không còn "Mã người nhận".
4. Xác nhận có "Email người nhận".
5. Xác nhận có "Họ và tên" và optional wording.
6. Chọn PDF test.
7. Chỉ nhập email.
8. Tạo bản cấp phát.
9. Tải file kết quả.
10. Verify lại exact file.
11. Nếu UI có detail page, xác nhận recipient được hiển thị human-friendly, nhưng UUID không cần lộ trong primary UX.
12. Lặp lại với cùng email khác casing nếu an toàn cho dữ liệu test.

## 11. Rollback criteria

Rollback ngay nếu sau deploy xuất hiện một trong các lỗi:

```text
không tạo issuance được
Manifest thiếu hoặc sai recipient_id
exact-file verification regression
duplicate Recipient hàng loạt
cross-organization recipient reuse
frontend submit 500
existing legacy tests fail trên production build
```

Rollback bằng deployment procedure hiện hữu và commit trước feature.

## 12. Documentation sau implementation

Không sửa `btl-nhom-9-knowledge-base.md` về mặt kiến trúc học thuật, vì task này không đổi semantics:

```text
recipient_id vẫn tồn tại
issuance_id vẫn tồn tại
Signed Manifest vẫn tồn tại
Production exact integrity vẫn như cũ
Research watermark vẫn như cũ
```

Có thể cập nhật release note hoặc UX documentation nếu repository có file tương ứng:

```text
Issue flow now accepts recipient email and optional full name.
recipient_id is resolved internally and no longer entered manually in the web UI.
```

Nếu slide đã chụp ảnh màn hình cũ có ô "Mã người nhận", nhắc thành viên thay screenshot mới.

## 13. Definition of Done

Chỉ được tuyên bố hoàn thành khi có fresh evidence cho toàn bộ checklist sau:

- [ ] `/issue` không còn yêu cầu nhập `recipient_id`.
- [ ] Email là bắt buộc ở new UX.
- [ ] Họ tên là optional.
- [ ] Email mới tạo Recipient.
- [ ] Email cũ reuse Recipient.
- [ ] Lookup email không phân biệt hoa thường trong scope hiện hữu.
- [ ] Tên trống vẫn issue được.
- [ ] Tên cũ không bị ghi đè ngầm.
- [ ] Invalid email bị từ chối.
- [ ] Cross-organization isolation không bị phá.
- [ ] Issuance vẫn lưu đúng internal `recipient_id`.
- [ ] Signed Manifest vẫn có đúng `recipient_id`.
- [ ] Legacy `recipient_id` API path vẫn chạy nếu quyết định giữ compatibility.
- [ ] Frontend typecheck PASS.
- [ ] Frontend full tests PASS.
- [ ] Backend relevant tests PASS.
- [ ] OpenAPI schema test PASS.
- [ ] Manual local issue + verify PASS.
- [ ] Production smoke test PASS sau deploy.
- [ ] Git diff không chứa thay đổi watermark, crypto hoặc benchmark ngoài scope.

## 14. Format báo cáo cuối mà agent phải trả về

Agent không được chỉ nói "đã hoàn thành".

Phải trả đúng cấu trúc:

```text
RESULT: READY hoặc NOT READY

1. Repository evidence
- branch:
- commit before:
- files changed:

2. Recipient model discovery
- model:
- email field:
- name field:
- organization scope:
- uniqueness rule:

3. API contract
- new fields:
- legacy recipient_id retained: yes/no
- resolver behavior:

4. Test evidence
- backend command + exact pass count:
- frontend typecheck:
- frontend test command + exact pass count:
- OpenAPI test:
- manual local smoke:

5. Production evidence
- deployed commit:
- health:
- /issue UI:
- email-only issuance:
- issue then verify:

6. Remaining limitations
- list concrete limitations only
```

Không dùng các câu như:

```text
production hoàn chỉnh
đã kiểm định tuyệt đối
không thể lỗi
100% an toàn
```

## 15. Implementation order tóm tắt cho agent yếu

Nếu agent dễ bị lạc scope, chỉ làm đúng thứ tự này:

```text
1. Read AGENTS/instructions.
2. Verify worktree and clean diff.
3. Read IssueDocumentPage.tsx.
4. Find exact issuance API and Recipient model.
5. If no Recipient entity, STOP with ARCHITECTURE GAP.
6. Write backend failing tests.
7. Run and observe RED.
8. Implement recipient email resolver minimally.
9. Run backend tests GREEN.
10. Write frontend failing tests.
11. Replace recipient UUID field with email + optional name.
12. Run frontend tests GREEN.
13. Sync OpenAPI/types.
14. Run full relevant regression suites.
15. Read git diff manually.
16. Local smoke issue -> download -> verify.
17. Commit.
18. Deploy using existing procedure only.
19. Production smoke.
20. Report exact evidence.
```

# Reference notes

Django supports database uniqueness constraints, including functional constraints using expressions such as `Lower(...)`. Only introduce such a migration if the existing Recipient schema actually requires it and the schema change has been reviewed.

Official Django reference:
https://docs.djangoproject.com/en/5.2/ref/models/constraints/

# Final scope reminder

Mục tiêu duy nhất của change này là:

```text
Human input:
email + optional full name

Internal identity:
recipient_id UUID

Bridge:
backend resolves email -> recipient_id

Everything after recipient_id:
keep existing issuance and cryptographic flow unchanged
```

Nếu agent bắt đầu chỉnh watermark, Ed25519, JCS, benchmark, deployment architecture hoặc redesign toàn app, agent đã đi sai scope.
