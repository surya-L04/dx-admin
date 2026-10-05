# DX-LR30 Admin

Interface Web d’administration pour le répéteur SPECTER DX-LR30.

## Fonctionnalités

- Connexion automatique au répéteur via USB/série
- Affichage de la version et de l’état du répéteur
- Statistiques RX / relais / pertes
- Informations radio
- Gestion de l’identité
- Voisins et nœuds Mesh
- Gestion des paramètres du répéteur
- Administration Remote Admin
- Modification du mot de passe Remote Admin
- Téléversement du firmware
- Interface Web en français

## Prérequis

- Python 3
- Flask
- pyserial
- Un SPECTER DX-LR30 connecté au système

## Installation

```bash
pip install flask pyserial
```

## Lancement

```bash
python3 app.py
```

L’interface Web est disponible sur le port 8085.

## Port série

Le débit série utilisé est de 115200 bauds.

Le périphérique USB du répéteur est détecté automatiquement.

## Attention

Cette application permet de modifier la configuration et le firmware du répéteur.

Vérifiez toujours le périphérique série avant toute opération d’écriture ou de flash.

## Projet

Projet expérimental destiné à faciliter l’administration des répéteurs SPECTER DX-LR30.

Ce projet n’est pas présenté comme un composant officiel de MeshCore.
