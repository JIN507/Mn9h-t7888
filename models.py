"""
Database Models

All SQLAlchemy models for the Bahith Al-Suwar application.
User-scoped models have user_id foreign key for isolation.
Shared catalog (countries, sources) is accessible to all users.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import uuid

db = SQLAlchemy()
bcrypt = Bcrypt()


def generate_uuid():
    """Generate UUID string for primary keys"""
    return str(uuid.uuid4())


# =============================================================================
# USER & AUTH
# =============================================================================

class User(db.Model):
    """User accounts with authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False, index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - user owns these (cascade delete)
    searches = db.relationship('Search', backref='user', lazy='dynamic', 
                               cascade='all, delete-orphan')
    analyses = db.relationship('Analysis', backref='user', lazy='dynamic',
                               cascade='all, delete-orphan')
    keywords = db.relationship('Keyword', backref='user', lazy='dynamic',
                               cascade='all, delete-orphan')
    files = db.relationship('UserFile', backref='user', lazy='dynamic',
                            cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """Verify password against hash"""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def to_dict(self, include_email=True):
        """Serialize user to dict"""
        data = {
            'id': self.id,
            'display_name': self.display_name,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_email:
            data['email'] = self.email
        return data
    
    def __repr__(self):
        return f'<User {self.email}>'


# =============================================================================
# SHARED CATALOG (All users see same data)
# =============================================================================

class Country(db.Model):
    """Countries catalog - shared across all users"""
    __tablename__ = 'countries'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    code = db.Column(db.String(5), unique=True, nullable=False, index=True)  # SA, US, EG
    name_ar = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sources = db.relationship('Source', backref='country', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name_ar': self.name_ar,
            'name_en': self.name_en,
            'is_active': self.is_active
        }
    
    def __repr__(self):
        return f'<Country {self.code}>'


class Source(db.Model):
    """News sources catalog - shared across all users"""
    __tablename__ = 'sources'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    country_id = db.Column(db.String(36), db.ForeignKey('countries.id'), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    domain = db.Column(db.String(255), unique=True, nullable=False, index=True)
    category = db.Column(db.String(50), index=True)  # news, social, gov, other
    logo_url = db.Column(db.String(500))
    is_verified = db.Column(db.Boolean, default=False, index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self, include_country=False):
        data = {
            'id': self.id,
            'name': self.name,
            'domain': self.domain,
            'category': self.category,
            'logo_url': self.logo_url,
            'is_verified': self.is_verified,
            'is_active': self.is_active
        }
        if include_country and self.country:
            data['country'] = self.country.to_dict()
        elif self.country_id:
            data['country_id'] = self.country_id
        return data
    
    def __repr__(self):
        return f'<Source {self.domain}>'


# =============================================================================
# USER-SCOPED DATA (Each user sees only their own)
# =============================================================================

class Keyword(db.Model):
    """User's saved keywords for monitoring"""
    __tablename__ = 'keywords'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), 
                        nullable=False, index=True)
    keyword = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'keyword', name='uq_user_keyword'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'keyword': self.keyword,
            'category': self.category,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Search(db.Model):
    """User's search history"""
    __tablename__ = 'searches'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    search_type = db.Column(db.String(30), nullable=False, index=True)  # direct, reverse, provenance
    query = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    image_hash = db.Column(db.String(64), index=True)
    result_count = db.Column(db.Integer, default=0)
    processing_time_ms = db.Column(db.Float)
    raw_response = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    results = db.relationship('SearchResult', backref='search', lazy='dynamic',
                              cascade='all, delete-orphan')
    
    def to_dict(self, include_results=False):
        data = {
            'id': self.id,
            'search_type': self.search_type,
            'query': self.query,
            'image_url': self.image_url,
            'result_count': self.result_count,
            'processing_time_ms': self.processing_time_ms,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_results:
            data['results'] = [r.to_dict() for r in self.results.limit(100)]
        return data


class SearchResult(db.Model):
    """Individual search results"""
    __tablename__ = 'search_results'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    search_id = db.Column(db.String(36), db.ForeignKey('searches.id', ondelete='CASCADE'),
                          nullable=False, index=True)
    source_id = db.Column(db.String(36), db.ForeignKey('sources.id'), nullable=True, index=True)
    url = db.Column(db.String(2000), nullable=False)
    title = db.Column(db.String(500))
    snippet = db.Column(db.Text)
    thumbnail_url = db.Column(db.String(500))
    domain = db.Column(db.String(255), index=True)
    published_at = db.Column(db.DateTime, index=True)
    confidence = db.Column(db.Float)
    rank = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    source = db.relationship('Source', backref='search_results')
    
    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'snippet': self.snippet,
            'thumbnail_url': self.thumbnail_url,
            'domain': self.domain,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'confidence': self.confidence,
            'rank': self.rank,
            'source': self.source.to_dict() if self.source else None
        }


class Analysis(db.Model):
    """User's AI detection analysis results"""
    __tablename__ = 'analyses'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    analysis_type = db.Column(db.String(30), nullable=False, index=True)  # ai_image, ai_audio, deepfake, video
    service = db.Column(db.String(50), nullable=False, index=True)  # thehive, aiornot, sightengine
    media_url = db.Column(db.String(500))
    media_hash = db.Column(db.String(64), index=True)
    is_ai_generated = db.Column(db.Boolean, index=True)
    confidence_ai = db.Column(db.Float)
    confidence_human = db.Column(db.Float)
    verdict = db.Column(db.String(100))
    generator = db.Column(db.String(100))
    detailed_results = db.Column(db.JSON)
    processing_time_ms = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    frames = db.relationship('AnalysisFrame', backref='analysis', lazy='dynamic',
                             cascade='all, delete-orphan')
    
    def to_dict(self, include_frames=False):
        data = {
            'id': self.id,
            'analysis_type': self.analysis_type,
            'service': self.service,
            'media_url': self.media_url,
            'is_ai_generated': self.is_ai_generated,
            'confidence_ai': self.confidence_ai,
            'confidence_human': self.confidence_human,
            'verdict': self.verdict,
            'generator': self.generator,
            'processing_time_ms': self.processing_time_ms,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_frames:
            data['frames'] = [f.to_dict() for f in self.frames.limit(200)]
        return data


class AnalysisFrame(db.Model):
    """Video frame analysis results"""
    __tablename__ = 'analysis_frames'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    analysis_id = db.Column(db.String(36), db.ForeignKey('analyses.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    frame_number = db.Column(db.Integer, nullable=False)
    timestamp_seconds = db.Column(db.Float, nullable=False)
    frame_url = db.Column(db.String(500))
    is_ai_generated = db.Column(db.Boolean)
    confidence = db.Column(db.Float)
    detection_result = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'frame_number': self.frame_number,
            'timestamp_seconds': self.timestamp_seconds,
            'frame_url': self.frame_url,
            'is_ai_generated': self.is_ai_generated,
            'confidence': self.confidence,
            'detection_result': self.detection_result
        }


class UserFile(db.Model):
    """User's exported/uploaded files - user-scoped storage"""
    __tablename__ = 'user_files'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)  # Original filename
    stored_filename = db.Column(db.String(255), nullable=False)  # UUID-based stored name
    file_type = db.Column(db.String(50), index=True)  # image, video, audio, report, export
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)  # Size in bytes
    file_path = db.Column(db.String(500), nullable=False)  # Relative path to storage
    description = db.Column(db.Text)
    source_feature = db.Column(db.String(50))  # Which feature generated this: ai_detection, search, etc
    is_public = db.Column(db.Boolean, default=False)  # Can be shared publicly
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self, include_user=False):
        data = {
            'id': self.id,
            'filename': self.filename,
            'file_type': self.file_type,
            'mime_type': self.mime_type,
            'file_size': self.file_size,
            'description': self.description,
            'source_feature': self.source_feature,
            'download_count': self.download_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_user and self.user:
            data['user'] = {
                'id': self.user.id,
                'display_name': self.user.display_name,
                'email': self.user.email
            }
        return data
    
    def __repr__(self):
        return f'<UserFile {self.filename}>'


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def init_db(app):
    """Initialize database with Flask app"""
    db.init_app(app)
    bcrypt.init_app(app)
    
    with app.app_context():
        db.create_all()


def get_or_create_source_by_domain(domain):
    """Get source by domain or return None"""
    if not domain:
        return None
    # Normalize domain
    domain = domain.lower().replace('www.', '')
    return Source.query.filter(Source.domain.ilike(f'%{domain}%')).first()
