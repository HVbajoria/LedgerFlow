from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('merchants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdempotencyKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=255)),
                ('request_hash', models.CharField(blank=True, max_length=64, null=True)),
                ('response_data', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='idempotency_keys', to='merchants.merchant')),
            ],
            options={
                'db_table': 'idempotency_keys',
            },
        ),
        migrations.CreateModel(
            name='Payout',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('amount_paise', models.BigIntegerField()),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], db_index=True, default='PENDING', max_length=10)),
                ('idempotency_key', models.CharField(max_length=255)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payouts', to='merchants.merchant')),
            ],
            options={
                'db_table': 'payouts',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['merchant', 'status'], name='idx_payout_merchant_status'), models.Index(fields=['idempotency_key'], name='idx_payout_idempotency_key')],
            },
        ),
        migrations.AddConstraint(
            model_name='payout',
            constraint=models.UniqueConstraint(fields=('merchant', 'idempotency_key'), name='uq_payout_merchant_idempotency_key'),
        ),
        migrations.AddIndex(
            model_name='idempotencykey',
            index=models.Index(fields=['merchant', 'key'], name='idx_idempotency_merchant_key'),
        ),
        migrations.AddIndex(
            model_name='idempotencykey',
            index=models.Index(fields=['expires_at'], name='idx_idempotency_expires_at'),
        ),
        migrations.AddConstraint(
            model_name='idempotencykey',
            constraint=models.UniqueConstraint(fields=('merchant', 'key'), name='uq_idempotency_merchant_key'),
        ),
    ]
