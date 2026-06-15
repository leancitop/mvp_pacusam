# Documentación de PACUSAM

Índice de la documentación del proyecto (MVP de curado de imágenes médicas con Active Learning).

## Para usar y entender el MVP
- [`manual.md`](manual.md) — manual de uso de cada pantalla + mapa feature → user story → archivo + glosario.

## Diseño y arquitectura
- [`arquitectura.md`](arquitectura.md) — arquitectura objetivo vs. estado del MVP + atributos de calidad ISO/IEC 25010.
- [`trazabilidad.md`](trazabilidad.md) — tabla de trazabilidad: cada decisión → cláusula del white paper + actividad del curso + riesgo + estado.

## Proceso (cómo se construyó)
- [`superpowers/specs/`](superpowers/specs/) — specs de diseño.
- [`superpowers/plans/`](superpowers/plans/) — planes de implementación TDD + reviews.

## Cómo correr
```bash
make install   # venv + dependencias
make run       # http://127.0.0.1:8000
make test      # suite de tests
make reset     # borrar la DB para re-sembrar
```
Credenciales demo: curador `demo@pacusam.org` / `demo1234` · admin `admin@pacusam.org` / `admin1234`.
