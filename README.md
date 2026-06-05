# Secure-Password-Manager-with-encryption
Secure password manager developed in Python using Tkinter. It allows users to safely store, organize, generate, and manage passwords through AES-encrypted storage, master password authentication, password strength analysis, auto-lock protection, clipboard auto-clear functionality, category-based organization.

##  Features

###  Security Features

* Master Password Authentication
* PBKDF2-HMAC-SHA256 Key Derivation (390,000 iterations)
* Fernet Encryption for password protection
* Encrypted credential storage
* Automatic vault locking after inactivity
* Secure clipboard auto-clear functionality
* Master password change support
* Password hashing with unique salt generation

###  Password Management

* Add, Edit, Delete, and View credentials
* Store:

  * Website/App Name
  * Username/Email
  * Password
  * URL
  * Notes
  * Category
* Real-time search functionality
* Category-based filtering
* Password visibility toggle
* One-click password copying

###  Password Generator

* Custom password length selection
* Uppercase letters option
* Lowercase letters option
* Numbers option
* Special symbols option
* Password strength evaluation
* Strong random password generation
* Instant password copy support

###  User Experience

* Modern dark theme interface
* Responsive desktop GUI
* Interactive toast notifications
* Password strength meter
* Professional dashboard layout
* Detail preview panel
* Entry statistics display
* Smooth hover effects and styling

###  Database Features

* SQLite database integration
* WAL (Write-Ahead Logging) support
* Automatic database initialization
* Indexed searching for faster performance
* Secure credential storage structure

### 🛠 Additional Utilities

* Plain-text JSON export functionality
* Clipboard management
* Auto-installation of cryptography dependency
* Session activity tracking
* Automatic inactivity monitoring
* Secure application locking and unlocking

##  Technologies Used

* Python
* Tkinter
* SQLite3
* Cryptography (Fernet)
* PBKDF2-HMAC-SHA256
* Threading
* Pyperclip

##  Use Cases

Vault Pro is ideal for:

* Personal password management
* Secure credential storage
* Cybersecurity learning projects
* Desktop security applications
* Educational encryption demonstrations

## Security Overview

Vault Pro protects sensitive information using:

* Fernet symmetric encryption
* PBKDF2-HMAC-SHA256 key derivation
* Salt-based password hashing
* Automatic session locking
* Clipboard sanitization

This project demonstrates practical implementation of cryptography, secure storage, authentication systems, and desktop application development using Python.

