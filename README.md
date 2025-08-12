# CastleSync
![GUI](https://i.imgur.com/wd0p6rU.png)

**Synchronisation SFTP de dossiers à la volée via Flask et Rclone**

## Fonctionnalités

* Interface web en Flask pour superviser et gérer les synchronisations SFTP en temps réel
* Synchronisation unidirectionnelle (copie) des fichiers distants vers le répertoire local
* Affichage des statistiques de transfert : pourcentage, vitesse, ETA, nombre et taille des fichiers
* Vérification automatique de la connexion SFTP et récupération de l'adresse IP WAN du serveur

## Prérequis

* **Python** 3.6+
* **Rclone** installé et disponible dans le dossier du script
* Bibliothèques Python (installables via pip) :
  * Flask
* Accès à un serveur SFTP pour la source distante

## Installation

1. Clonez ce dépôt :

   ```bash
   git clone https://github.com/YourUser/CastleTracker.git
   cd CastleTracker
   ```
2. Copiez le fichier de configuration et ajustez-le :

   ```bash
   cp settings.conf settings.conf.local  # ou renommez selon vos habitudes
   ```
3. Assurez-vous que `rclone` est accessible et configuré sur votre machine.

## Configuration

Éditez `settings.conf` (ou `settings.conf.local`) pour renseigner vos chemins et identifiants :

```ini
[paths]
rclone_path = /chemin/vers/rclone      # Chemin vers l'exécutable rclone

[remote]
host = exemple.com                     # Hôte SFTP
port = 22                               # Port SFTP (par défaut 22)
user = utilisateur                      # Nom d'utilisateur SFTP
password = mot_de_passe                 # Mot de passe SFTP
path = /chemin/distant                  # Répertoire source distant

[local]
default_path = /chemin/local         # Chemin du dossier de destination local
```

## Usage

* **Windows** : double-cliquez sur `build.bat` pour lancer l'application.
* **Linux/macOS** : lancez manuellement :

  ```bash
  python app.py
  ```
* Ouvrez votre navigateur sur :

  ```
  ```

[http://localhost:12000](http://localhost:12000)

```
- Interface :
  - **📦 Scanner** : met à jour les statistiques (fichiers, taille, IP, connexion SFTP)  
  - **🚀 Transférer** : démarre la copie des fichiers via rclone  
  - **⏹ Stop** : interrompt le transfert en cours  
  - **🔄 Reset Source** : vide le répertoire source distant après confirmation  

```
## Licence

Ce projet est sous licence **CC BY-NC-SA 4.0**  

---  
*Développé par Félix Abt – Cairn Studios*

```
