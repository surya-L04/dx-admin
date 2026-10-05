# DX-LR30 Admin

Interface Web d’administration pour les répéteurs **SPECTER DX-LR30**.

`dx-admin` fournit une interface Web légère permettant de surveiller et administrer un répéteur DX-LR30 connecté en USB/série.

Le projet est destiné aux utilisateurs et développeurs travaillant avec des équipements SPECTER / MeshCore.

## Présentation

L'objectif de `dx-admin` est de proposer une interface d'administration simple et accessible depuis un navigateur, sans avoir à utiliser directement le terminal ou les commandes série du répéteur.

L'application communique avec le DX-LR30 via son interface série USB et présente les informations importantes dans une interface Web en français.

## Fonctionnalités

### Supervision

* Connexion automatique au répéteur via USB/série
* Détection du périphérique série
* Affichage de la version du firmware
* Affichage de l'état du répéteur
* Uptime
* Compteurs RX
* Compteurs de relais
* Compteurs de paquets perdus
* RSSI / SNR
* Informations radio

### Réseau Mesh

* Informations sur l'identité du répéteur
* Liste des voisins
* Liste des nœuds
* Informations Mesh
* Informations sur les rooms

### Administration

* Gestion des paramètres du répéteur
* Interface Remote Admin
* Modification du mot de passe Remote Admin
* Téléversement du firmware
* Interface Web en français

## Architecture

Le projet est volontairement léger.

```text
Navigateur Web
      │
      ▼
   Flask
      │
      ▼
    dx-admin
      │
      │ USB / série
      ▼
 SPECTER DX-LR30
      │
      ▼
   MeshCore
```

L'application Flask assure l'interface Web et la communication avec le périphérique série.

Le DX-LR30 reste responsable de la communication radio et du fonctionnement du répéteur.

## Matériel

Le projet est conçu pour fonctionner avec un :

* SPECTER DX-LR30
* ordinateur ou Raspberry Pi sous Linux
* connexion USB au répéteur

Le périphérique série est détecté automatiquement lorsqu'il correspond au contrôleur USB utilisé par le DX-LR30.

## Prérequis

* Linux
* Python 3
* Flask
* pyserial
* SPECTER DX-LR30 connecté en USB

Installation des dépendances :

```bash
pip install flask pyserial
```

## Lancement

Depuis le répertoire du projet :

```bash
python3 app.py
```

L'interface Web écoute par défaut sur :

```text
http://<adresse-ip>:8085
```

## Port série

Le débit série utilisé est :

```text
115200 bauds
```

Le périphérique USB du répéteur est détecté automatiquement.

Le port série peut également être défini dans l'application lorsque cela est nécessaire.

## Sécurité

L'interface permet d'effectuer des opérations d'administration sur le répéteur, notamment la modification de paramètres et le téléversement d'un firmware.

Il est donc recommandé de :

* ne pas exposer directement le port Web sur Internet ;
* utiliser un réseau de confiance ;
* vérifier le périphérique série avant toute opération d'écriture ;
* vérifier le firmware avant tout flash ;
* utiliser un mot de passe Remote Admin approprié.

## Firmware

Le firmware du DX-LR30 n'est pas inclus dans ce dépôt.

Le projet `dx-admin` est uniquement l'interface d'administration.

Les firmwares SPECTER / MeshCore doivent être distribués séparément et installés selon les procédures prévues par leurs projets respectifs.

## Développement

Le projet est développé en Python avec Flask.

Structure principale :

```text
dx-admin/
├── app.py
├── templates/
│   └── index.html
├── README.md
└── .gitignore
```

Les fichiers temporaires, sauvegardes, logs, environnements virtuels et fichiers générés localement sont volontairement exclus du dépôt.

## État du projet

`dx-admin` est un projet expérimental destiné à faciliter l'administration des répéteurs SPECTER DX-LR30.

L'interface et les fonctions peuvent évoluer en fonction des besoins du matériel et du protocole Remote Admin.

Les contributions, retours et améliorations sont les bienvenus.

## Relation avec MeshCore

Ce projet est conçu pour fonctionner avec des équipements et logiciels liés à l'écosystème SPECTER / MeshCore.

Il ne s'agit pas d'un composant officiel de MeshCore et n'est pas présenté comme tel.

## Contribution

Les développeurs intéressés peuvent proposer :

* corrections de bugs ;
* améliorations de l'interface ;
* nouvelles fonctions Remote Admin ;
* amélioration de la détection série ;
* support de nouvelles versions du firmware ;
* améliorations de sécurité ;
* documentation.

Les Pull Requests et retours techniques sont les bienvenus.

## Licence

La licence du projet doit être définie avant une utilisation ou une redistribution officielle.

