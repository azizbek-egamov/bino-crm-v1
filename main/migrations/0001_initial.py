# Generated by Django 5.1.4 on 2025-06-15 10:11

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BotUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telegram_id', models.BigIntegerField(unique=True)),
                ('first_name', models.CharField(blank=True, max_length=255, null=True)),
                ('language', models.CharField(choices=[('uz_latin', "O'zbekcha (Lotin)"), ('uz_cyrillic', 'Ўзбекча (Кирил)'), ('russian', 'Русский')], default='uz_latin', max_length=20)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Bot Foydalanuvchisi',
                'verbose_name_plural': 'Bot Foydalanuvchilari',
            },
        ),
        migrations.CreateModel(
            name='City',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Shahar nomi')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqti')),
            ],
            options={
                'verbose_name': 'Shahar',
                'verbose_name_plural': 'Shaharlar',
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='ClientInformation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=150, verbose_name="To'liq ism")),
                ('phone', models.CharField(max_length=255, null=True, verbose_name='Telefon raqam')),
                ('phone2', models.CharField(blank=True, max_length=255, null=True, verbose_name='Telefon raqam 2')),
                ('heard', models.CharField(choices=[('Telegramda', 'Telegramda'), ('Instagramda', 'Instagramda'), ('YouTubeda', 'YouTubeda'), ('Odamlar orasida', 'Odamlar orasida'), ('Xech qayerda', 'Xech qayerda')], max_length=200, verbose_name='Qayerda eshitgan')),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': "Mijoz ma'lumoti",
                'verbose_name_plural': "Mijoz ma'lumotlari",
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='ExpenseType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Chiqim turi')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqti')),
            ],
            options={
                'verbose_name': 'Chiqim turi',
                'verbose_name_plural': 'Chiqim turlari',
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='HomeInformation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('padez_number', models.IntegerField(verbose_name='Padez raqami')),
                ('home_number', models.CharField(max_length=200, verbose_name='Uy raqami')),
                ('home_floor', models.IntegerField(verbose_name='Qavat')),
                ('xona', models.IntegerField(verbose_name='Xonalar soni')),
                ('field', models.FloatField(verbose_name='Uy maydoni (m/kv)')),
                ('price', models.PositiveIntegerField(verbose_name='Uy narxi')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqti')),
                ('home_model_id', models.IntegerField(null=True, verbose_name='Home model ID')),
                ('busy', models.BooleanField(default=False, verbose_name='Band')),
                ('floor_plan', models.ImageField(blank=True, null=True, upload_to='floor_plans/', verbose_name='Loyiha rasmi')),
                ('floor_plan_drawing', models.ImageField(blank=True, null=True, upload_to='floor_plan_drawings/', verbose_name='Chertoj rasmi')),
            ],
            options={
                'verbose_name': "Uy ma'lumoti",
                'verbose_name_plural': "Uy ma'lumotlari",
                'ordering': ['padez_number', 'home_floor', 'home_number'],
            },
        ),
        migrations.CreateModel(
            name='Building',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='Bino nomi')),
                ('code', models.CharField(blank=True, max_length=3, null=True, verbose_name='Bino shifri')),
                ('podezd', models.IntegerField(verbose_name='Podezdlar soni')),
                ('apartments', models.JSONField(verbose_name='Xonadonlar soni')),
                ('floor', models.IntegerField(verbose_name='Qavatlar')),
                ('status', models.BooleanField(default=False, verbose_name="Qo'shilgan")),
                ('location', models.TextField(blank=True, null=True, verbose_name='Bino joylashuvi')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqti')),
                ('city', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.city', verbose_name='Shahar')),
            ],
            options={
                'verbose_name': 'Bino',
                'verbose_name_plural': 'Binolar',
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.IntegerField(verbose_name='Summa')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Izoh')),
                ('payment_type', models.CharField(choices=[('Naqd', 'Naqd'), ('Plastik', 'Plastik'), ("Hisobdan o'tkazish", "Hisobdan o'tkazish")], default='Naqd', max_length=50, verbose_name="To'lov turi")),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan sana')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name="O'zgartirilgan sana")),
                ('building', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.building', verbose_name='Bino')),
                ('expense_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.expensetype', verbose_name='Chiqim turi')),
            ],
            options={
                'verbose_name': 'Chiqim',
                'verbose_name_plural': 'Chiqimlar',
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='Home',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqt')),
                ('building', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='homes', to='main.building', verbose_name='Bino')),
                ('home', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='home_instances', to='main.homeinformation', verbose_name='Uy')),
            ],
            options={
                'verbose_name': 'Uy',
                'verbose_name_plural': 'Uylar',
                'ordering': ['-created'],
                'unique_together': {('building', 'home')},
            },
        ),
        migrations.CreateModel(
            name='ClientTrash',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('passport', models.CharField(max_length=15, verbose_name='Passport')),
                ('term', models.IntegerField(verbose_name="To'lov muddati (oy)")),
                ('payment', models.PositiveIntegerField(verbose_name="Oldindan to'lov")),
                ('residual', models.DecimalField(decimal_places=0, editable=False, max_digits=50, verbose_name="Qolgan to'lov")),
                ('oylik_tolov', models.DecimalField(decimal_places=0, editable=False, max_digits=50, verbose_name="Oylik to'lov")),
                ('count_month', models.IntegerField(editable=False, verbose_name='Qolgan oylar')),
                ('status', models.CharField(max_length=20, verbose_name='Holati')),
                ('debt', models.BooleanField(default=False, verbose_name='Qarzdor')),
                ('created', models.DateTimeField(verbose_name='Yaratilgan vaqti')),
                ('trash_created', models.DateTimeField(auto_now_add=True, verbose_name='Savatda yaratilgan')),
                ('client', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.clientinformation', verbose_name='Mijoz')),
                ('home', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='main.home', verbose_name='Uy')),
            ],
            options={
                'verbose_name': "O'chirilgan shartnoma",
                'verbose_name_plural': "O'chirilgan shartnomalar",
                'ordering': ['-trash_created'],
            },
        ),
        migrations.CreateModel(
            name='Client',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contract', models.PositiveIntegerField(blank=True, null=True, verbose_name='Shartnoma raqami')),
                ('passport', models.CharField(max_length=15, verbose_name='Passport')),
                ('passport_muddat', models.CharField(max_length=25, null=True, verbose_name='Berilgan vaqti')),
                ('given', models.CharField(max_length=100, null=True, verbose_name='Berilgan joyi')),
                ('location', models.CharField(max_length=255, null=True, verbose_name='Manzili')),
                ('location2', models.CharField(blank=True, max_length=255, null=True, verbose_name='Manzili 2')),
                ('term', models.IntegerField(verbose_name="To'lov muddati (oy)")),
                ('payment', models.PositiveIntegerField(verbose_name="Oldindan to'lov")),
                ('home_price', models.PositiveIntegerField(blank=True, null=True, verbose_name='Xonadon narxi')),
                ('pay_date', models.PositiveIntegerField(blank=True, null=True, verbose_name="To'lov qilish sanasi")),
                ('residual', models.DecimalField(decimal_places=0, editable=False, max_digits=50, verbose_name="Qolgan to'lov")),
                ('oylik_tolov', models.DecimalField(decimal_places=0, editable=False, max_digits=50, verbose_name="Oylik to'lov")),
                ('count_month', models.IntegerField(editable=False, verbose_name='Qolgan oylar')),
                ('residu', models.IntegerField(editable=False, null=True, verbose_name="Oydan qogan to'lov")),
                ('status', models.CharField(choices=[('Rasmiylashtirilmoqda', 'Rasmiylashtirilmoqda'), ('Rasmiylashtirilgan', 'Rasmiylashtirilgan'), ('Bekor qilingan', 'Bekor qilingan'), ('Tugallangan', 'Tugallangan')], max_length=20, verbose_name='Holati')),
                ('debt', models.BooleanField(default=False, verbose_name='Qarzdor')),
                ('created', models.DateTimeField(null=True, verbose_name='Yaratilgan vaqti')),
                ('client', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='contracts', to='main.clientinformation', verbose_name='Mijoz')),
                ('home', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='contracts', to='main.home', verbose_name='Uy')),
            ],
            options={
                'verbose_name': 'Shartnoma',
                'verbose_name_plural': 'Shartnomalar',
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='Rasrochka',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.IntegerField(verbose_name='Oy raqami')),
                ('amount', models.IntegerField(verbose_name="To'lov miqdori")),
                ('amount_paid', models.IntegerField(default=0, verbose_name="To'langan miqdor")),
                ('qoldiq', models.IntegerField(editable=False, verbose_name='Oy uchun qoldiq')),
                ('pay_date', models.DateTimeField(blank=True, null=True, verbose_name="O'xirgi to'lov sanasi")),
                ('date', models.DateTimeField(verbose_name="To'lov sanasi")),
                ('client', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='main.client', verbose_name='Mijoz')),
            ],
            options={
                'verbose_name': "To'lov",
                'verbose_name_plural': "To'lovlar",
                'ordering': ['client', 'month'],
            },
        ),
    ]
