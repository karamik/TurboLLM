// ========================================================================
// firmware_signer_check.sv – проверка цифровой подписи прошивки
// Защита от загрузки поддельного кода (трояны, OTA-атаки)
// Использует аппаратный акселератор ECDSA (упрощённо – SHA-256 хеш)
// ========================================================================

module firmware_signer_check (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        firmware_loaded,   // сигнал, что прошивка загружена в SRAM
    input  logic [31:0] firmware_size,     // размер прошивки в байтах
    input  logic [255:0] expected_hash,    // ожидаемый хеш (подпись) – из eFuse
    input  logic        public_key_valid,  // публичный ключ загружен
    input  logic        test_mode,
    output logic        signature_ok,      // HIGH – подпись верна
    output logic        sign_error,        // HIGH – ошибка подписи (блокировка)
    output logic [255:0] computed_hash     // вычисленный хеш (для отладки)
);

    // Акселератор SHA-256 (упрощённая модель – только для симуляции)
    // В реальном ASIC используется аппаратный SHA-256 модуль.
    logic [255:0] hash_reg;
    logic hash_computed;

    // Эмуляция вычисления хеша (в реальности – чтение из SRAM)
    // Здесь мы используем простой CRC для демонстрации.
    // В реальном проекте подключается SHA-256 ядро.
    logic [31:0] crc;
    logic [31:0] crc_next;
    logic [31:0] byte_cnt;
    logic [7:0]  mem_byte;

    // Простейший CRC-32 для имитации (не для продакшена!)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            crc <= 32'hFFFFFFFF;
            byte_cnt <= 32'h0;
            hash_computed <= 1'b0;
        end else if (firmware_loaded && !hash_computed && !test_mode) begin
            // Симуляция чтения байт из SRAM (в реальности – память)
            // Для простоты используем счётчик как "данные"
            crc_next = {crc[30:0], crc[31] ^ crc[21] ^ crc[1] ^ crc[0]};
            crc <= crc_next;
            byte_cnt <= byte_cnt + 1;
            if (byte_cnt >= firmware_size - 1) begin
                hash_reg <= {crc, 224'h0}; // расширяем до 256 бит
                hash_computed <= 1'b1;
            end
        end
    end

    // Сравнение с ожидаемым хешем
    logic sig_ok, sig_err;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sig_ok  <= 1'b0;
            sig_err <= 1'b0;
        end else if (hash_computed && public_key_valid) begin
            if (hash_reg == expected_hash) begin
                sig_ok  <= 1'b1;
                sig_err <= 1'b0;
            end else begin
                sig_ok  <= 1'b0;
                sig_err <= 1'b1;
            end
        end
    end

    assign signature_ok   = sig_ok;
    assign sign_error     = sig_err;
    assign computed_hash  = hash_reg;

endmodule
