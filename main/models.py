from django.db import models
from django.utils import timezone

class City(models.Model):
    name = models.CharField(max_length=100, verbose_name="Shahar nomi")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Shahar"
        verbose_name_plural = "Shaharlar"
        ordering = ['-created']

class Building(models.Model):
    city = models.ForeignKey(to=City, on_delete=models.SET_NULL, null=True, verbose_name="Shahar")
    name = models.CharField(max_length=150, verbose_name="Bino nomi")
    code = models.CharField(max_length=3, null=True, blank=True, verbose_name="Bino shifri")
    podezd = models.IntegerField(verbose_name="Podezdlar soni")
    apartments = models.JSONField(verbose_name="Xonadonlar soni")
    floor = models.IntegerField(verbose_name="Qavatlar")
    status = models.BooleanField(verbose_name="Qo'shilgan", default=False)
    location = models.TextField(verbose_name="Bino joylashuvi", null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")
    

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Bino"
        verbose_name_plural = "Binolar"
        ordering = ['-created']

class HomeInformation(models.Model):
    padez_number = models.IntegerField(verbose_name="Padez raqami")
    home_number = models.CharField(max_length=200, verbose_name="Uy raqami")
    home_floor = models.IntegerField(verbose_name="Qavat")
    xona = models.IntegerField(verbose_name="Xonalar soni")
    field = models.FloatField(verbose_name="Uy maydoni (m/kv)")
    price = models.PositiveIntegerField(verbose_name="Uy narxi")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")
    home_model_id = models.IntegerField(verbose_name="Home model ID", null=True)
    busy = models.BooleanField(verbose_name="Band", default=False)
    floor_plan = models.ImageField(upload_to='floor_plans/', null=True, blank=True, verbose_name="Loyiha rasmi")
    floor_plan_drawing = models.ImageField(upload_to='floor_plan_drawings/', null=True, blank=True, verbose_name="Chertoj rasmi")
    
    def __str__(self):
        return f"{self.home_number} - uy, {self.padez_number} - padez"
    
    class Meta:
        verbose_name = "Uy ma'lumoti"
        verbose_name_plural = "Uy ma'lumotlari"
        ordering = ['padez_number', 'home_floor', 'home_number']

class Home(models.Model):
    building = models.ForeignKey(to=Building, on_delete=models.CASCADE, verbose_name="Bino", related_name="homes")
    home = models.ForeignKey(to=HomeInformation, on_delete=models.CASCADE, verbose_name="Uy", related_name="home_instances")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    
    def __str__(self):
        return f"{self.building.name} - {self.home.home_number}"
    
    class Meta:
        verbose_name = "Uy"
        verbose_name_plural = "Uylar"
        ordering = ['-created']
        unique_together = ['building', 'home']

class ClientInformation(models.Model):
    full_name = models.CharField(max_length=150, verbose_name="To'liq ism")
    phone = models.CharField(max_length=255, verbose_name="Telefon raqam", null=True)
    phone2 = models.CharField(max_length=255, verbose_name="Telefon raqam 2", null=True, blank=True)
    heard = models.CharField(max_length=200, verbose_name="Qayerda eshitgan", choices=[
        ('Telegramda', 'Telegramda'),
        ('Instagramda', 'Instagramda'),
        ('YouTubeda', 'YouTubeda'),
        ('Odamlar orasida', 'Odamlar orasida'),
        ('Xech qayerda', 'Xech qayerda'),
    ])
    created = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.full_name
    
    class Meta:
        verbose_name = "Mijoz ma'lumoti"
        verbose_name_plural = "Mijoz ma'lumotlari"
        ordering = ['-created']

class Client(models.Model):
    """Shartnoma"""
    STATUS_CHOICES = [
        ('Rasmiylashtirilmoqda', 'Rasmiylashtirilmoqda'),
        ('Rasmiylashtirilgan', 'Rasmiylashtirilgan'),
        ('Bekor qilingan', 'Bekor qilingan'),
        ('Tugallangan', 'Tugallangan'),
    ]
    
    client = models.ForeignKey(to=ClientInformation, on_delete=models.SET_NULL, null=True, verbose_name="Mijoz", related_name="contracts")
    contract = models.PositiveIntegerField(verbose_name="Shartnoma raqami", null=True, blank=True)
    home = models.ForeignKey(to=Home, on_delete=models.SET_NULL, null=True, verbose_name="Uy", related_name="contracts")
    passport = models.CharField(max_length=15, verbose_name="Passport")
    passport_muddat = models.CharField(max_length=25, verbose_name="Berilgan vaqti", null=True)
    given = models.CharField(max_length=100, verbose_name="Berilgan joyi", null=True)
    location = models.CharField(max_length=255, verbose_name="Manzili", null=True)
    location2 = models.CharField(max_length=255, verbose_name="Manzili 2", null=True, blank=True)
    term = models.IntegerField(verbose_name="To'lov muddati (oy)")
    payment = models.PositiveIntegerField(verbose_name="Oldindan to'lov")
    home_price = models.PositiveIntegerField(verbose_name="Xonadon narxi", null=True, blank=True)
    pay_date = models.PositiveIntegerField(verbose_name="To'lov qilish sanasi", null=True, blank=True)
    residual = models.DecimalField(max_digits=50, decimal_places=0, editable=False, verbose_name="Qolgan to'lov")
    oylik_tolov = models.DecimalField(max_digits=50, decimal_places=0, editable=False, verbose_name="Oylik to'lov")
    count_month = models.IntegerField(editable=False, verbose_name="Qolgan oylar")
    residu = models.IntegerField(editable=False, null=True, verbose_name="Oydan qogan to'lov")
    status = models.CharField(max_length=20, verbose_name="Holati", choices=STATUS_CHOICES)
    debt = models.BooleanField(default=False, verbose_name="Qarzdor")
    created = models.DateTimeField(verbose_name="Yaratilgan vaqti", null=True)
    
    def __str__(self):
        return f"{self.contract}"
    
    class Meta:
        verbose_name = "Shartnoma"
        verbose_name_plural = "Shartnomalar"
        ordering = ['-created']
        
    def save(self, *args, **kwargs):
        # Shartnoma yaratilganda, uyni band qilish
        if not self.pk:  # Yangi obyekt yaratilayotgan bo'lsa
            if self.home and self.home.home:
                self.home.home.busy = True
                self.home.home.save()
                
        super().save(*args, **kwargs)

class Rasrochka(models.Model):
    client = models.ForeignKey(to=Client, on_delete=models.CASCADE, null=True, verbose_name="Mijoz", related_name="payments")
    month = models.IntegerField(verbose_name="Oy raqami")
    amount = models.IntegerField(verbose_name="To'lov miqdori")
    amount_paid = models.IntegerField(verbose_name="To'langan miqdor", default=0)
    qoldiq = models.IntegerField(verbose_name="Oy uchun qoldiq", editable=False)
    pay_date = models.DateTimeField(verbose_name="O'xirgi to'lov sanasi", null=True, blank=True)
    date = models.DateTimeField(verbose_name="To'lov sanasi")

    def save(self, *args, **kwargs):
        self.qoldiq = self.amount - self.amount_paid
        if not self.pay_date and self.amount_paid > 0:
            self.pay_date = timezone.now()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.client} - {self.month}-oy"
    
    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ['client', 'month']

class ClientTrash(models.Model):
    client = models.ForeignKey(to=ClientInformation, on_delete=models.SET_NULL, null=True, verbose_name="Mijoz")
    home = models.ForeignKey(to=Home, on_delete=models.SET_NULL, null=True, verbose_name="Uy")
    passport = models.CharField(max_length=15, verbose_name="Passport")
    term = models.IntegerField(verbose_name="To'lov muddati (oy)")
    payment = models.PositiveIntegerField(verbose_name="Oldindan to'lov")
    residual = models.DecimalField(max_digits=50, decimal_places=0, editable=False, verbose_name="Qolgan to'lov")
    oylik_tolov = models.DecimalField(max_digits=50, decimal_places=0, editable=False, verbose_name="Oylik to'lov")
    count_month = models.IntegerField(editable=False, verbose_name="Qolgan oylar")
    status = models.CharField(max_length=20, verbose_name="Holati")
    debt = models.BooleanField(default=False, verbose_name="Qarzdor")
    created = models.DateTimeField(verbose_name="Yaratilgan vaqti")
    trash_created = models.DateTimeField(auto_now_add=True, verbose_name="Savatda yaratilgan")
    
    def __str__(self):
        return f"{self.client.full_name} - O'chirilgan"
    
    class Meta:
        verbose_name = "O'chirilgan shartnoma"
        verbose_name_plural = "O'chirilgan shartnomalar"
        ordering = ['-trash_created']

class ExpenseType(models.Model):
    name = models.CharField(max_length=200, verbose_name="Chiqim turi")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Chiqim turi"
        verbose_name_plural = "Chiqim turlari"
        ordering = ['-created']

class Expense(models.Model):
    expense_type = models.ForeignKey(ExpenseType, on_delete=models.CASCADE, verbose_name="Chiqim turi")
    building = models.ForeignKey(Building, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Bino")
    amount = models.IntegerField(verbose_name="Summa")
    description = models.TextField(null=True, blank=True, verbose_name="Izoh")
    payment_type = models.CharField(max_length=50, choices=[
        ('Naqd', 'Naqd'),
        ('Plastik', 'Plastik'),
        ('Hisobdan o\'tkazish', 'Hisobdan o\'tkazish')
    ], default='Naqd', verbose_name="To'lov turi")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan sana")
    updated = models.DateTimeField(auto_now=True, verbose_name="O'zgartirilgan sana")
    
    class Meta:
        verbose_name = "Chiqim"
        verbose_name_plural = "Chiqimlar"
        ordering = ['-created']

    def __str__(self):
        return f"{self.expense_type.name} - {self.amount:,} so'm"


class BotUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    language = models.CharField(max_length=20, default='uz_latin', choices=[
        ('uz_latin', 'O\'zbekcha (Lotin)'),
        ('uz_cyrillic', 'Ўзбекча (Кирил)'),
        ('russian', 'Русский'),
    ])
    created = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.first_name} ({self.telegram_id})"
    
    class Meta:
        verbose_name = "Bot Foydalanuvchisi"
        verbose_name_plural = "Bot Foydalanuvchilari"