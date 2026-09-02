# TP1 — Conceptos básicos para la construcción de Sistemas Distribuidos

Universidad Nacional de Luján · Departamento de Ciencias Básicas
Sistemas Distribuidos y Programación Paralela — 2026 · Dr. David Petrocelli

**Entrega:** viernes 04/09/2026

## Integrantes y reparto

| Integrante | Rol | Hits |
|---|---|---|
| Agustina Ortiz | Plataforma — repo, CI/CD, nube y entrega | 1, 2, 3 |
| _por completar_ | Nodo C — transporte y RPC | 4, 5, 8 |
| _por completar_ | Nodo D — registro, coordinación y pruebas de integración | 6, 7 |

Cada quien escribe el `README.md` de sus propios Hits y su parte del informe, apenas los termina.

---

## El contrato

Estas decisiones se cerraron antes de empezar a codear. **Si alguna se cambia, se avisa al grupo y se actualiza acá**, porque los tres frentes dependen de ellas.

### 1. Lenguaje

Python 3.11. Sockets en la biblioteca estándar, `grpcio` para el Hit 8, `pytest` para las pruebas.

### 2. Estructura del repositorio

```
common/     código compartido: logger, protocolo, parseo de parámetros
hit1/ … hit8/   un directorio y un README.md por ejercicio
tests/      pruebas automatizadas
docs/       informe, diagramas y video
```

Los Hits 1 a 3 son archivos chicos que se copian y evolucionan. **Del Hit 4 en adelante todos importan `common/`**, para no arrastrar el mismo bug tres veces.

### 3. Formato de los mensajes

Un objeto JSON por línea, terminado en `\n` (NDJSON):

```json
{"tipo":"saludo","from":{"host":"10.0.0.5","port":52341},"ts":"2026-09-03T18:04:11Z","msg":"hola"}
{"tipo":"ack","from":{"host":"10.0.0.6","port":9002},"ts":"2026-09-03T18:04:11Z","ref":"2026-09-03T18:04:11Z"}
```

El delimitador no es un detalle estético: **TCP es un stream de bytes y no preserva los límites de los mensajes**. Un `recv()` puede devolver dos saludos pegados o medio saludo. `common.protocol.LectorDeLineas` resuelve el framing; nadie debería volver a escribir esa lógica.

### 4. API del nodo D

| Método | Ruta | Devuelve |
|---|---|---|
| `POST` | `/register` | `{"ventana": "...", "peers": [{"host","port"}, ...]}` |
| `GET` | `/peers` | Los nodos C de la ventana **actual** |
| `GET` | `/health` | Estado del servicio — es el endpoint público que pide el enunciado |

```json
{
  "servicio": "registro-d",
  "estado": "ok",
  "nodos_activos": 3,
  "uptime_s": 842,
  "ventana_actual": "2026-09-04T11:29:00Z"
}
```

### 5. Registro de actividades

`common/logger.py` escribe una línea JSON por evento a `logs/<nodo>.log` y a `stderr`, y mantiene los últimos 500 eventos en memoria. Resuelve de una vez el requisito de llevar logs **en memoria y disco**, y es lo que alimenta el contador de `/health`.

### 6. Puertos

| Nodo | Puerto |
|---|---|
| D (HTTP) | `8000` |
| D (gRPC, Hit 8) | `50051` |
| C (Hits 1–5) | `9001` y `9002` |
| C (Hits 6–8) | aleatorio, vía `bind(('', 0))` |

Con puerto aleatorio, C tiene que **leer cuál le tocó** con `getsockname()[1]` antes de anunciarse a D.

### 7. Quién escribe cada README

El autor del Hit, apenas lo termina. Las decisiones de diseño solo las conoce quien las tomó. Los diagramas van en **Mermaid dentro del propio README**: es texto, versiona en Git y GitHub lo renderiza sin herramientas externas. La plantilla común está en [`docs/plantilla-readme-hit.md`](docs/plantilla-readme-hit.md).

### 8. Quién escribe cada sección del informe

Misma regla que los README: el informe no lo escribe una sola persona.

| Integrante | Secciones |
|---|---|
| A · Nodo C | Sus Hits (4, 5, 8), la comparación JSON vs Protobuf y los diagramas globales |
| B · Nodo D | Sus Hits (6, 7) y la evidencia de dos ventanas consecutivas |
| C · Plataforma | Introducción, arquitectura general, falacias, herramientas de IA, conclusiones y ensamblado |

El esqueleto con todas las secciones ya tituladas está en [`docs/informe.md`](docs/informe.md).

### 9. Video

El enunciado pide una grabación subida al repositorio. **Decisión pendiente del grupo:** si se reemplaza por la presentación en clase, conviene igual grabar esa presentación y subirla a `docs/video/` — cuesta cero horas y cierra un requisito explícito.

---

## Puesta en marcha

```bash
git clone https://github.com/agustina-ortiz/TP1-SDyPP.git
cd TP1-SDyPP

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest -v
```

## Seguridad

- El `.env` real **nunca** se commitea. La plantilla vacía está en `.env.example`.
- El pipeline corre [gitleaks](https://github.com/gitleaks/gitleaks) sobre el repositorio y su historial completo, y **falla** si detecta un secreto.
- Si se filtra una credencial: revocarla y generar otra. Borrar la línea no alcanza, queda en el historial de Git.

## Documentación

- [Informe](docs/informe.md)
- [Plantilla de README por Hit](docs/plantilla-readme-hit.md)
- Video: `docs/video/`
