# mvp_pacusam

MVP de **PACUSAM** (*PlAtaforma de CUrado de imágenes médicas de la unSAM*). Plataforma de curado/etiquetado de imágenes médicas con validación asistida por *Active Learning*. Trabajo Práctico Final Integrador, Grupo 9, Ingeniería de Software (LCD-UNSAM).

## Problema

Los investigadores del CIMeT dedican ~80% del tiempo a etiquetar imágenes manualmente. PACUSAM transforma ese etiquetado manual en **validación asistida**: el modelo propone, la persona valida.


## Estructura del repo

```
mvp_pacusam/
├── README.md
├── .gitignore
└── docs/
    └── arquitectura.md   # arquitectura objetivo (Pipes & Filters + Layers + Pub-Sub)
```

El MVP (M2) es un *walking skeleton* sobre datos mockeados.