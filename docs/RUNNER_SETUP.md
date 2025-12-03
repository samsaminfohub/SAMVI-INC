# Configuration du Self-Hosted Runner GitHub Actions

Ce guide explique comment configurer un runner GitHub Actions sur votre machine Windows pour déclencher automatiquement des builds Docker locaux.

## Prérequis

- Windows 10/11
- Docker Desktop installé et en cours d'exécution
- Droits administrateur sur votre machine
- Accès au dépôt GitHub

## Étape 1 : Accéder aux Paramètres du Runner

1. Allez sur votre dépôt GitHub : `https://github.com/samsaminfohub/SAMVI-INC`
2. Cliquez sur **Settings** (Paramètres)
3. Dans le menu de gauche, cliquez sur **Actions** > **Runners**
4. Cliquez sur **New self-hosted runner**
5. Sélectionnez **Windows** comme système d'exploitation

## Étape 2 : Télécharger et Installer le Runner

GitHub affichera des commandes à exécuter. Ouvrez **PowerShell en tant qu'administrateur** et exécutez :

```powershell
# Créer un dossier pour le runner
mkdir actions-runner; cd actions-runner

# Télécharger le runner (la commande exacte sera fournie par GitHub)
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.XXX.X/actions-runner-win-x64-2.XXX.X.zip -OutFile actions-runner-win-x64-2.XXX.X.zip

# Extraire l'archive
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD/actions-runner-win-x64-2.XXX.X.zip", "$PWD")
```

## Étape 3 : Configurer le Runner

Exécutez la commande de configuration fournie par GitHub (elle contiendra votre token unique) :

```powershell
./config.cmd --url https://github.com/samsaminfohub/SAMVI-INC --token VOTRE_TOKEN_ICI
```

Lors de la configuration, répondez aux questions :
- **Runner group** : Appuyez sur Entrée (défaut)
- **Runner name** : Donnez un nom (ex: `windows-local`)
- **Labels** : Tapez `windows` (important !)
- **Work folder** : Appuyez sur Entrée (défaut)

## Étape 4 : Démarrer le Runner

### Option A : Exécution Interactive (pour tester)

```powershell
./run.cmd
```

Le runner s'exécutera dans cette fenêtre PowerShell. **Ne fermez pas la fenêtre.**

### Option B : Exécution en tant que Service (recommandé)

Pour que le runner démarre automatiquement avec Windows :

```powershell
# Installer en tant que service
./svc.sh install

# Démarrer le service
./svc.sh start
```

## Étape 5 : Vérifier Docker Desktop

Assurez-vous que Docker Desktop est :
1. **Démarré** et en cours d'exécution
2. Configuré pour démarrer automatiquement avec Windows (Settings > General > Start Docker Desktop when you log in)

## Étape 6 : Tester le Workflow

1. Faites un commit sur la branche `main`
2. Allez dans l'onglet **Actions** de votre dépôt GitHub
3. Vous devriez voir le workflow `Deploy Streamlit App` s'exécuter
4. Le job `docker-build-local` devrait s'exécuter sur votre machine

## Vérification Locale

Pendant l'exécution du workflow, vous pouvez vérifier sur votre machine :

```powershell
# Voir les conteneurs en cours d'exécution
docker ps

# Voir les logs
docker-compose logs -f
```

## Arrêter le Runner

### Si exécution interactive :
Appuyez sur `Ctrl+C` dans la fenêtre PowerShell

### Si exécution en tant que service :
```powershell
./svc.sh stop
./svc.sh uninstall
```

## Dépannage

### Le runner ne démarre pas
- Vérifiez que Docker Desktop est en cours d'exécution
- Redémarrez le service runner

### Le workflow échoue
- Vérifiez les logs dans l'onglet Actions de GitHub
- Assurez-vous que le fichier `docker-compose.yml` est présent dans le dépôt
- Vérifiez que les ports 8501, 9000, 9001, 8000 ne sont pas déjà utilisés

### Erreur "docker-compose: command not found"
Docker Desktop pour Windows inclut `docker-compose`. Si l'erreur persiste, essayez :
```powershell
docker compose version
```

## Sécurité

> [!WARNING]
> Le runner peut exécuter du code sur votre machine. Si votre dépôt est public ou si d'autres personnes y ont accès, soyez conscient des risques.

**Recommandations :**
- Gardez votre dépôt privé si possible
- Limitez les accès au dépôt
- Surveillez les workflows qui s'exécutent
