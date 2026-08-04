# Huong dan cai dat

## 1. Tao Personal Access Token (PAT)
GitHub -> avatar goc tren phai -> Settings -> Developer settings ->
Personal access tokens -> Tokens (classic) -> Generate new token.
Chon scope: `repo` va `read:user`. Copy token lai (chi hien 1 lan).

## 2. Them token vao repo dac biet cua ban
Vao repo `<TEN_GITHUB_CUA_BAN>/<TEN_GITHUB_CUA_BAN>` -> Settings ->
Secrets and variables -> Actions -> New repository secret.
- Name: `ACCESS_TOKEN`
- Value: token vua copy o buoc 1

## 3. Sua README.md
Mo README.md, thay `<TEN_GITHUB_CUA_BAN>` bang username GitHub that cua ban
(xuat hien 6 lan trong file).

## 4. Push code len repo
Xem huong dan chi tiet trong tin nhan chat.

## 5. Chay thu workflow
Vao tab Actions cua repo -> chon workflow "Update profile stats" ->
Run workflow (nut mau xanh) -> doi khoang 1-2 phut -> kiem tra file
light_mode.svg / dark_mode.svg co duoc cap nhat so lieu that khong.

## Luu y
- Lan chay dau tien co the mat vai phut vi phai quet toan bo commit
  trong tat ca repo cua ban de tinh Lines of Code.
- Cac lan chay sau se nhanh hon nho co file cache trong thu muc cache/.
- Neu ban co rat nhieu repo/commit, GitHub GraphQL co the bi rate-limit;
  script se tu dong doi va thu lai.
