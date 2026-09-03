#!/bin/sh
# Publica SimLeón en GitHub Pages (https://enrique-am.github.io/simleon/)
# Requiere: git y la CLI de GitHub (brew install gh && gh auth login), o crea el repo a mano en github.com/new
set -e
cd "$(dirname "$0")"
git init -q 2>/dev/null || true
git add -A
git commit -qm "SimLeón: mapa isométrico en pixel art de León, Gto. (77 cuadros, 2048 px)" || true
git branch -M main
if command -v gh >/dev/null; then
  gh repo view enrique-am/simleon >/dev/null 2>&1 || gh repo create enrique-am/simleon --public --description "SimLeón — León, Guanajuato en pixel art isométrico" --homepage https://enrique-am.github.io/simleon/
  git remote get-url origin >/dev/null 2>&1 || git remote add origin https://github.com/enrique-am/simleon.git
  git push -u origin main
  gh api -X POST repos/enrique-am/simleon/pages -f 'source[branch]=main' -f 'source[path]=/docs' >/dev/null 2>&1 || gh api -X PUT repos/enrique-am/simleon/pages -f 'source[branch]=main' -f 'source[path]=/docs' >/dev/null
  echo "Listo: https://enrique-am.github.io/simleon/  (tarda 1-2 min en aparecer)"
else
  echo "Crea el repo vacío en https://github.com/new (nombre: simleon, público) y luego:"
  echo "  git remote add origin https://github.com/enrique-am/simleon.git && git push -u origin main"
  echo "  Settings → Pages → Source: Deploy from a branch → main, carpeta /docs"
fi
