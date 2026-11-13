/*
 FILA TRANSACIONAL - MODELO PARA REVISAO DO DBA (SQL Server 2022+).
 NAO EXECUTADO, NAO AUTORIZA DEPLOY, NAO INCLUI CONTAS/GRANT/POST.
 Banco, schema, indices, permissoes, backup e rollback sao responsabilidade do DBA.
 Cada documento pertence a um lote_id, sem confundir lote_id com contrato_id.
 Nao faz download/upload nem processa dbo.conte_lote/fn_g1865.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* Executar somente em DB HML autorizado, apos BACKUP e revisao do DBA. */
CREATE TABLE dbo.FilaDocumentoPdfHml (
    ItemId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_FilaDocumentoPdfHml PRIMARY KEY,
    Idempotencia char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    LoteId nvarchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ContratoId nvarchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    DocumentoId nvarchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    Versao nvarchar(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    HashEsperado char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
    BytesEsperados bigint NOT NULL,
    Estado varchar(24) NOT NULL CONSTRAINT DF_FilaDocumentoPdfHml_Estado DEFAULT ('PENDENTE'),
    Geracao bigint NOT NULL CONSTRAINT DF_FilaDocumentoPdfHml_Geracao DEFAULT (0),
    Token uniqueidentifier NULL,
    LeaseAteUtc datetime2(3) NULL,
    ReciboReadback nvarchar(256) NULL,
    CriadoUtc datetime2(3) NOT NULL CONSTRAINT DF_FilaDocumentoPdfHml_Criado DEFAULT SYSUTCDATETIME(),
    AtualizadoUtc datetime2(3) NOT NULL CONSTRAINT DF_FilaDocumentoPdfHml_Atualizado DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_FilaDocumentoPdfHml_Idempotencia UNIQUE (Idempotencia),
    CONSTRAINT UQ_FilaDocumentoPdfHml_Documento UNIQUE (ContratoId, DocumentoId, Versao),
    CONSTRAINT CK_FilaDocumentoPdfHml_Tamanho CHECK (BytesEsperados > 0 AND BytesEsperados <= 8388608),
    CONSTRAINT CK_FilaDocumentoPdfHml_Geracao CHECK (Geracao >= 0),
    CONSTRAINT CK_FilaDocumentoPdfHml_Estado CHECK
        (Estado IN ('PENDENTE','RESERVADO','INCERTO_UPLOAD','CONFIRMADO_UPLOAD','BLOQUEADO'))
);
GO
CREATE INDEX IX_FilaDocumentoPdfHml_Estado ON dbo.FilaDocumentoPdfHml(Estado, ItemId);
GO

CREATE OR ALTER PROCEDURE dbo.fila_pdf_hml_enfileirar
    @Idempotencia char(64), @LoteId nvarchar(64), @ContratoId nvarchar(64),
    @DocumentoId nvarchar(64), @Versao nvarchar(64),
    @HashEsperado char(64), @BytesEsperados bigint
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @Idempotencia IS NULL OR LEN(@Idempotencia) <> 64 OR
       @Idempotencia COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       @HashEsperado IS NULL OR LEN(@HashEsperado) <> 64 OR
       @HashEsperado COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       @BytesEsperados NOT BETWEEN 1 AND 8388608 OR
       @LoteId IS NULL OR LEN(@LoteId) NOT BETWEEN 1 AND 64 OR
       @ContratoId IS NULL OR LEN(@ContratoId) NOT BETWEEN 1 AND 64 OR
       @DocumentoId IS NULL OR LEN(@DocumentoId) NOT BETWEEN 1 AND 64 OR
       @Versao IS NULL OR LEN(@Versao) NOT BETWEEN 1 AND 64 OR
       @LoteId COLLATE Latin1_General_100_BIN2 LIKE '%[^A-Za-z0-9_-]%' OR
       @ContratoId COLLATE Latin1_General_100_BIN2 LIKE '%[^A-Za-z0-9_-]%' OR
       @DocumentoId COLLATE Latin1_General_100_BIN2 LIKE '%[^A-Za-z0-9_-]%' OR
       @Versao COLLATE Latin1_General_100_BIN2 LIKE '%[^A-Za-z0-9_-]%'
        THROW 51000, 'Manifesto invalido', 1;

    BEGIN TRANSACTION;
        DECLARE @AntigoHash char(64), @AntigoBytes bigint,
                @AntigoLote nvarchar(64), @OutraChave char(64);
        SELECT @AntigoHash = HashEsperado, @AntigoBytes = BytesEsperados,
               @AntigoLote = LoteId
          FROM dbo.FilaDocumentoPdfHml WITH (UPDLOCK, HOLDLOCK)
         WHERE Idempotencia = @Idempotencia;
        SELECT @OutraChave = Idempotencia
          FROM dbo.FilaDocumentoPdfHml WITH (UPDLOCK, HOLDLOCK)
         WHERE ContratoId = @ContratoId AND DocumentoId = @DocumentoId AND Versao = @Versao;
        IF @OutraChave IS NOT NULL AND @OutraChave <> @Idempotencia
            THROW 51001, 'Documento ja registrado em outro lote', 1;
        IF @AntigoHash IS NOT NULL
        BEGIN
            IF @AntigoHash <> @HashEsperado OR @AntigoBytes <> @BytesEsperados OR @AntigoLote <> @LoteId
                THROW 51002, 'Mesmo ID com manifesto divergente', 1;
        END
        ELSE
            INSERT dbo.FilaDocumentoPdfHml
                (Idempotencia,LoteId,ContratoId,DocumentoId,Versao,HashEsperado,BytesEsperados)
            VALUES (@Idempotencia,@LoteId,@ContratoId,@DocumentoId,@Versao,@HashEsperado,@BytesEsperados);
    COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE dbo.fila_pdf_hml_reservar
    @SegundosLease int = 60
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @SegundosLease IS NULL OR @SegundosLease NOT BETWEEN 30 AND 300
        THROW 51010, 'Lease invalido', 1;

    BEGIN TRANSACTION;
        DECLARE @Resultado int;
        EXEC @Resultado = sys.sp_getapplock
             @Resource = N'fila_pdf_hml_reserva_unica', @LockMode = 'Exclusive',
             @LockOwner = 'Transaction', @LockTimeout = 0;
        IF @Resultado < 0
            THROW 51011, 'Reserva concorrente em andamento', 1;
        -- Nenhum reclaim automatico, nem mesmo apos vencimento do lease.
        -- Um estado INCERTO requer GET do destino, nao retry do upload.
        IF EXISTS(SELECT 1 FROM dbo.FilaDocumentoPdfHml WITH (UPDLOCK, HOLDLOCK)
                  WHERE Estado IN ('RESERVADO','INCERTO_UPLOAD'))
            THROW 51012, 'Reserva ativa ou upload incerto: reconciliacao exigida', 1;

        DECLARE @Agora datetime2(3) = SYSUTCDATETIME();
        DECLARE @Token uniqueidentifier = NEWID();
        ;WITH Escolhido AS (
            SELECT TOP(1) * FROM dbo.FilaDocumentoPdfHml WITH (UPDLOCK, HOLDLOCK)
            WHERE Estado='PENDENTE' ORDER BY ItemId
        )
        UPDATE Escolhido
           SET Estado='RESERVADO', Token=@Token, Geracao=Geracao+1,
               LeaseAteUtc=DATEADD(SECOND,@SegundosLease,@Agora), AtualizadoUtc=@Agora
        OUTPUT inserted.ItemId,inserted.Idempotencia,inserted.LoteId,
               inserted.ContratoId,inserted.DocumentoId,inserted.Versao,
               inserted.HashEsperado,inserted.BytesEsperados,
               inserted.Token,inserted.Geracao,inserted.LeaseAteUtc;
    COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE dbo.fila_pdf_hml_marcar_incerto
    @ItemId bigint, @Token uniqueidentifier, @Geracao bigint
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF @ItemId IS NULL OR @Token IS NULL OR @Geracao IS NULL
        THROW 51020, 'Posse obrigatoria', 1;
    BEGIN TRANSACTION;
        UPDATE dbo.FilaDocumentoPdfHml
           SET Estado='INCERTO_UPLOAD', AtualizadoUtc=SYSUTCDATETIME()
         WHERE ItemId=@ItemId AND Token=@Token AND Geracao=@Geracao
           AND Estado='RESERVADO' AND LeaseAteUtc > SYSUTCDATETIME();
        IF @@ROWCOUNT <> 1
            THROW 51021, 'Lease expirado, posse perdida ou estado invalido', 1;
    COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE dbo.fila_pdf_hml_confirmar_readback
    @ItemId bigint, @Token uniqueidentifier, @Geracao bigint,
    @HashObservado char(64), @BytesObservados bigint, @Recibo nvarchar(256)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    -- A aplicacao devera comprovar GET autenticado no destino. Este SP nao faz rede
    -- nem autentica @Recibo. Somente executar apos readback independente auditado.
    IF @ItemId IS NULL OR @Token IS NULL OR @Geracao IS NULL OR
       @HashObservado IS NULL OR LEN(@HashObservado) <> 64 OR
       @HashObservado COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9a-f]%' OR
       @BytesObservados IS NULL OR @BytesObservados <= 0 OR
       @Recibo IS NULL OR LEN(@Recibo) < 8
        THROW 51030, 'Evidencia de readback invalida', 1;
    BEGIN TRANSACTION;
        UPDATE dbo.FilaDocumentoPdfHml
           SET Estado='CONFIRMADO_UPLOAD', ReciboReadback=@Recibo,
               AtualizadoUtc=SYSUTCDATETIME()
         WHERE ItemId=@ItemId AND Token=@Token AND Geracao=@Geracao
           AND Estado='INCERTO_UPLOAD' AND LeaseAteUtc>SYSUTCDATETIME()
           AND HashEsperado=@HashObservado AND BytesEsperados=@BytesObservados;
        IF @@ROWCOUNT <> 1
            THROW 51031, 'Readback nao confere, lease perdeu validade ou estado mudou', 1;
    COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE dbo.fila_pdf_hml_resumo
AS
BEGIN
    SET NOCOUNT ON;
    SELECT Estado,COUNT_BIG(*) AS Quantidade
      FROM dbo.FilaDocumentoPdfHml GROUP BY Estado;
END;
GO
